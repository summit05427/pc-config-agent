import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import type { RuntimeMessage } from '../runtime/types'

const envMock = vi.hoisted(() => ({
  appEnv: 'development',
  openUiEnabled: true,
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
  })

  it('用户消息保持原有气泡渲染', () => {
    render(<MessageItem message={createMessage('user', '帮我做一个行程')} threadId="item-thread" />)

    expect(screen.getByText('帮我做一个行程')).toBeInTheDocument()
    expect(screen.queryByText('助手')).toBeNull()
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
})
