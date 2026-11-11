import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./request', () => ({
  requestAgentJson: vi.fn(),
  requestAgentVoid: vi.fn(),
}))

import { requestAgentJson, requestAgentVoid } from './request'
import {
  deleteSession,
  deleteSessions,
  getSessionMessages,
  listSessions,
  renameSession,
  setSessionArchived,
  setSessionsArchived,
  setSessionModel,
  setSessionPinned,
} from './sessions'

describe('sessions api', () => {
  beforeEach(() => {
    vi.mocked(requestAgentJson).mockResolvedValue({})
    vi.mocked(requestAgentVoid).mockResolvedValue(undefined)
  })

  it('会话列表默认分页为第 1 页 20 条', async () => {
    await listSessions()
    expect(requestAgentJson).toHaveBeenCalledWith(
      '/sessions',
      { method: 'GET' },
      { page: 1, size: 20, archived: 'false' },
    )
  })

  it('归档列表传 archived=true', async () => {
    await listSessions(1, 50, true)
    expect(requestAgentJson).toHaveBeenCalledWith(
      '/sessions',
      { method: 'GET' },
      { page: 1, size: 50, archived: 'true' },
    )
  })

  it('置顶与归档以 PUT 提交布尔值', async () => {
    await setSessionPinned('thread-1', true)
    expect(requestAgentJson).toHaveBeenCalledWith('/sessions/thread-1/pin', {
      method: 'PUT',
      body: JSON.stringify({ pinned: true }),
      headers: { 'Content-Type': 'application/json' },
    })

    await setSessionArchived('thread-1', true)
    expect(requestAgentJson).toHaveBeenCalledWith('/sessions/thread-1/archive', {
      method: 'PUT',
      body: JSON.stringify({ archived: true }),
      headers: { 'Content-Type': 'application/json' },
    })
  })

  it('历史消息带分页与读取方向，并对 threadId 编码', async () => {
    vi.mocked(requestAgentJson).mockResolvedValueOnce({
      thread_id: 'thread/1',
      list: [],
      total: 0,
      page: 2,
      size: 10,
    })
    await getSessionMessages('thread/1', 2, 10, 'desc')
    expect(requestAgentJson).toHaveBeenCalledWith(
      '/sessions/thread%2F1/messages',
      { method: 'GET' },
      { page: 2, size: 10, order: 'desc' },
    )
  })

  it('把历史消息里的原始 hitl 载荷解析为表单结构', async () => {
    vi.mocked(requestAgentJson).mockResolvedValueOnce({
      thread_id: 'thread-1',
      list: [
        { role: 'user', content: '预算 8000 元' },
        {
          role: 'assistant',
          content: '是否继续查看这份方案？',
          hitl: {
            interrupt_id: 'int-1',
            interaction_type: 'confirm_compatibility',
            question: '是否继续查看这份方案？',
            input_schema: { fields: [], submit_label: '确认' },
            context: {},
            schema_version: '1',
          },
        },
      ],
      total: 2,
      page: 1,
      size: 20,
    })

    const result = await getSessionMessages('thread-1')

    expect(result.list[0]?.hitl).toBeUndefined()
    expect(result.list[1]?.hitl).toEqual({
      interruptId: 'int-1',
      interactionType: 'confirm_compatibility',
      question: '是否继续查看这份方案？',
      fields: [],
      submitLabel: '确认',
      context: {},
      schemaVersion: '1',
    })
  })

  it('历史 hitl 载荷不完整时省略该字段而不是透传', async () => {
    vi.mocked(requestAgentJson).mockResolvedValueOnce({
      thread_id: 'thread-1',
      list: [{ role: 'assistant', content: '待确认', hitl: { question: '缺 id' } }],
      total: 1,
      page: 1,
      size: 20,
    })

    const result = await getSessionMessages('thread-1')

    expect(result.list[0]).not.toHaveProperty('hitl')
    expect(result.list[0]?.content).toBe('待确认')
  })

  it('重命名以 PATCH 提交 JSON', async () => {
    await renameSession('thread-1', '新标题')
    expect(requestAgentJson).toHaveBeenCalledWith('/sessions/thread-1', {
      method: 'PATCH',
      body: JSON.stringify({ title: '新标题' }),
      headers: { 'Content-Type': 'application/json' },
    })
  })

  it('删除会话使用无响应体的 void 请求', async () => {
    await deleteSession('thread-1')
    expect(requestAgentVoid).toHaveBeenCalledWith('/sessions/thread-1', {
      method: 'DELETE',
    })
  })

  it('批量归档逐条提交、静默错误并汇总成功与失败', async () => {
    vi.mocked(requestAgentJson)
      .mockResolvedValueOnce({})
      .mockRejectedValueOnce(new Error('boom'))

    const result = await setSessionsArchived(['thread-1', 'thread-2'], true)

    expect(result).toEqual({ succeeded: ['thread-1'], failed: ['thread-2'] })
    expect(requestAgentJson).toHaveBeenCalledWith('/sessions/thread-1/archive', {
      method: 'PUT',
      body: JSON.stringify({ archived: true }),
      headers: { 'Content-Type': 'application/json' },
      silent: true,
    })
  })

  it('批量删除使用静默 DELETE 并汇总结果', async () => {
    vi.mocked(requestAgentVoid)
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error('boom'))

    const result = await deleteSessions(['thread-1', 'thread-2'])

    expect(result).toEqual({ succeeded: ['thread-1'], failed: ['thread-2'] })
    expect(requestAgentVoid).toHaveBeenCalledWith('/sessions/thread-1', {
      method: 'DELETE',
      silent: true,
    })
  })

  it('切换会话模型传 model_key，并关闭自动 toast 由调用方回滚', async () => {
    await setSessionModel('thread-1', 'openai:gpt-4o')
    expect(requestAgentJson).toHaveBeenCalledWith('/sessions/thread-1/model', {
      method: 'PUT',
      body: JSON.stringify({ model_key: 'openai:gpt-4o' }),
      headers: { 'Content-Type': 'application/json' },
      silent: true,
    })
  })
})
