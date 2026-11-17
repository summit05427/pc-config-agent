import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import type { RuntimeMessage } from '../runtime/types'

const envMock = vi.hoisted(() => ({
  appEnv: 'development',
  openUiEnabled: true,
  showExecutionTrace: false,
}))

vi.mock('@/shared/lib/env', () => ({ env: envMock }))

import { MessageItem } from './message-item'

beforeAll(async () => {
  await import('@/features/generative-ui/components/openui-renderer-runtime')
})

const createMessage = (
  role: RuntimeMessage['role'],
  content: string,
  status: RuntimeMessage['status'] = 'done',
): RuntimeMessage => ({
  id: 'message-1',
  role,
  content,
  reasoning: '',
  steps: [],
  status,
  createdAt: 0,
})

describe('MessageItem', () => {
  beforeEach(() => {
    envMock.openUiEnabled = true
    envMock.showExecutionTrace = false
  })

  it('用户消息保持原有气泡渲染', () => {
    render(<MessageItem message={createMessage('user', '帮我做一个行程')} threadId="item-thread" />)

    expect(screen.getByText('帮我做一个行程')).toBeInTheDocument()
    expect(screen.queryByText('助手')).toBeNull()
  })

  it('HITL 提问与正文相同时只渲染一次', () => {
    const question = '已有 8 项兼容性检查通过，但 1 项因数据缺失无法确认。是否继续查看这份方案？'
    render(
      <MessageItem
        message={{
          ...createMessage('assistant', question, 'awaiting_input'),
          hitl: {
            interruptId: 'int-1',
            interactionType: 'compatibility_confirmation',
            question,
            fields: [],
            submitLabel: '继续',
            context: {},
          },
        }}
        threadId="item-thread"
      />,
    )

    expect(screen.getAllByText(question)).toHaveLength(1)
  })

  it('助手消息中的 OpenUI 块可交互并透传会话与动作', async () => {
    const onContinueConversation = vi.fn()
    render(
      <MessageItem
        message={createMessage(
          'assistant',
          '```openui\nroot = Stack([Text("动态内容", "heading"), Button("继续")])\n```',
        )}
        threadId="item-thread"
        onContinueConversation={onContinueConversation}
      />,
    )

    expect(await screen.findByRole('heading', { name: '动态内容' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '继续' }))

    expect(onContinueConversation).toHaveBeenCalledWith('继续')
  })

  it('思考与阶段指示器并存，不暴露工具执行轨迹与等待文本', () => {
    render(
      <MessageItem
        message={{
          ...createMessage('assistant', '', 'pending'),
          reasoning: '先确认预算与使用场景，再决定性能侧重点。',
          steps: [
            {
              id: 'step-1',
              name: 'search_hardware_candidates',
              args: '{}',
              result: '',
              status: 'running',
              startedAt: 0,
              finishedAt: null,
            },
          ],
        }}
        threadId="item-thread"
      />,
    )

    expect(screen.getByText(/先确认预算与使用场景/)).toBeInTheDocument()
    expect(screen.queryByText(/search_hardware_candidates/)).not.toBeInTheDocument()
    expect(screen.queryByText('等待响应')).not.toBeInTheDocument()
    // 思考面板与阶段指示器同时存在，用户既能看到思考也能看到当前阶段
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByText('正在检索候选硬件')).toBeInTheDocument()
  })

  it('工具事件尚未到达时用节点阶段推进文案', () => {
    render(
      <MessageItem
        message={{ ...createMessage('assistant', '', 'pending'), stage: 'strategizing' }}
        threadId="item-thread"
      />,
    )

    expect(screen.getByText('正在制定配置策略')).toBeInTheDocument()
    expect(screen.queryByText('正在解析需求')).not.toBeInTheDocument()
  })

  it('没有思考内容时只渲染一组三点加载动画', () => {
    render(
      <MessageItem message={createMessage('assistant', '', 'pending')} threadId="item-thread" />,
    )

    expect(screen.getAllByRole('status')).toHaveLength(1)
    expect(screen.queryByText('等待响应')).not.toBeInTheDocument()
  })

  it('开发开关打开时才展示执行轨迹', () => {
    envMock.showExecutionTrace = true

    render(
      <MessageItem
        message={{
          ...createMessage('assistant', '', 'pending'),
          steps: [
            {
              id: 'step-1',
              name: 'search_hardware_candidates',
              args: '{}',
              result: '',
              status: 'running',
              startedAt: 0,
              finishedAt: null,
            },
          ],
        }}
        threadId="item-thread"
      />,
    )

    // 轨迹展示业务阶段文案，原始工具名保留在 title 供排查
    expect(screen.getByTitle('search_hardware_candidates')).toBeInTheDocument()
    expect(screen.getAllByText('正在检索候选硬件').length).toBeGreaterThan(0)
  })
})
