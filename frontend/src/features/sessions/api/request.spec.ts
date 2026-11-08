import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({ toast: { error: vi.fn() } }))
// 本地 `.env.local` 可能把 Agent 基址覆盖成绝对地址，这里固定契约默认值，
// 保证 URL 拼接用例不受开发者本机配置影响
vi.mock('@/shared/lib/env', () => ({ env: { agentBaseUrl: '/agent/api/v1' } }))

import { toast } from 'sonner'

import {
  ApiError,
  NETWORK_ERROR_MESSAGE,
  acceptToken,
  configureAuth,
  getAccessToken,
  normalizeError,
  resetAuthForTests,
} from '@/core/http'

import {
  INVALID_RESPONSE_MESSAGE,
  buildAgentUrl,
  requestAgentJson,
  requestAgentVoid,
  sendAgentRequest,
} from './request'

const createJsonResponse = (payload: unknown, status = 200): Response =>
  new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

/** 等待请求失败并归一化错误，避免 catch 分支把成功值混入断言 */
const captureError = async (promise: Promise<unknown>): Promise<ApiError> => {
  try {
    await promise
  } catch (reason) {
    return normalizeError(reason)
  }
  throw new Error('预期请求失败但成功返回')
}

describe('buildAgentUrl', () => {
  it('拼接 Agent 前缀并保留查询参数', () => {
    const url = new URL(buildAgentUrl('/sessions', { page: 1, size: 20 }))

    expect(url.pathname).toBe('/agent/api/v1/sessions')
    expect(url.searchParams.get('page')).toBe('1')
    expect(url.searchParams.get('size')).toBe('20')
  })

  it('忽略 undefined 参数，路径缺少前导斜杠时自动补全', () => {
    const url = new URL(buildAgentUrl('sessions', { empty: undefined }))

    expect(url.pathname).toBe('/agent/api/v1/sessions')
    expect(url.search).toBe('')
  })
})

describe('Agent 请求', () => {
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
    resetAuthForTests()
    configureAuth({ refresh: async () => null, onUnauthorized: () => undefined })
  })

  it('成功响应直接返回解析后的 JSON', async () => {
    fetchMock.mockResolvedValue(createJsonResponse({ list: [], total: 0 }))

    await expect(requestAgentJson('/sessions', { method: 'GET' })).resolves.toEqual({
      list: [],
      total: 0,
    })
  })

  it('响应体不是合法 JSON 时抛出解析失败', async () => {
    fetchMock.mockResolvedValue(new Response('not-json', { status: 200 }))

    await expect(requestAgentJson('/sessions', { method: 'GET' })).rejects.toMatchObject({
      message: INVALID_RESPONSE_MESSAGE,
    })
  })

  it('204 删除请求不尝试解析响应体', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))

    await expect(requestAgentVoid('/sessions/1', { method: 'DELETE' })).resolves.toBeUndefined()
  })

  it('网络异常转换为统一文案与错误码', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    await expect(
      sendAgentRequest('/sessions', { method: 'GET', silent: true }),
    ).rejects.toMatchObject({
      message: NETWORK_ERROR_MESSAGE,
      code: 'NETWORK_ERROR',
    })
  })

  it('主动取消保持 AbortError，便于调用方区分用户停止', async () => {
    const abortError = new DOMException('aborted', 'AbortError')
    fetchMock.mockRejectedValue(abortError)

    await expect(
      sendAgentRequest('/chat/stream', { method: 'POST', signal: new AbortController().signal }),
    ).rejects.toBe(abortError)
  })

  it('401 先刷新再重放一次，重放使用新 Token', async () => {
    let refreshCount = 0
    configureAuth({
      refresh: async () => {
        refreshCount += 1
        acceptToken('fresh-token')
        return 'fresh-token'
      },
      onUnauthorized: () => undefined,
    })
    acceptToken('expired-token')

    let attempt = 0
    const authorizations: Array<string | null> = []
    fetchMock.mockImplementation(async (_input, init) => {
      attempt += 1
      const headers = (init?.headers ?? {}) as Record<string, string>
      authorizations.push(headers.Authorization ?? null)
      if (attempt === 1) {
        return createJsonResponse({ code: 'UNAUTHORIZED', message: 'expired' }, 401)
      }
      return createJsonResponse({ ok: true })
    })

    await expect(requestAgentJson('/sessions', { method: 'GET' })).resolves.toEqual({ ok: true })
    expect(refreshCount).toBe(1)
    expect(authorizations).toEqual(['Bearer expired-token', 'Bearer fresh-token'])
    expect(attempt).toBe(2)
  })

  it('刷新不可用时清理登录态并通知路由', async () => {
    const onUnauthorized = vi.fn()
    configureAuth({ refresh: async () => null, onUnauthorized })
    acceptToken('expired-token')

    fetchMock.mockResolvedValue(createJsonResponse({ message: 'expired' }, 401))

    await expect(
      sendAgentRequest('/sessions', { method: 'GET', silent: true }),
    ).rejects.toBeInstanceOf(ApiError)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
    expect(getAccessToken()).toBe('')
  })

  it('404 静默返回业务结果，不弹全局提示', async () => {
    fetchMock.mockResolvedValue(createJsonResponse({ message: '会话不存在' }, 404))

    await expect(
      sendAgentRequest('/sessions/unknown', { method: 'GET', silent: true }),
    ).rejects.toMatchObject({ status: 404, message: '会话不存在' })
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('非 404 的 HTTP 错误按配置弹提示', async () => {
    fetchMock.mockResolvedValue(createJsonResponse({ message: '参数错误' }, 400))

    await expect(sendAgentRequest('/sessions', { method: 'GET' })).rejects.toMatchObject({
      status: 400,
      message: '参数错误',
    })
    expect(toast.error).toHaveBeenCalledWith('参数错误')
  })

  it('错误体使用 detail 字段或状态码文案兜底', async () => {
    fetchMock
      .mockResolvedValueOnce(createJsonResponse({ detail: '详情错误' }, 400))
      .mockResolvedValueOnce(new Response('<html>bad gateway</html>', { status: 500 }))

    const detailError = await captureError(
      sendAgentRequest('/sessions', { method: 'GET', silent: true }),
    )
    const fallbackError = await captureError(
      sendAgentRequest('/sessions', { method: 'GET', silent: true }),
    )

    expect(detailError.message).toBe('详情错误')
    expect(fallbackError.message).toBe('服务器内部错误')
  })
})
