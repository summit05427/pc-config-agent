import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getMock, putMock, deleteMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  putMock: vi.fn(),
  deleteMock: vi.fn(),
}))

// 只替换传输层：feedback/api 仍走真实实现，查询 key 与请求拼装都在测试覆盖范围内
vi.mock('@/core/http', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/core/http')>()
  return {
    ...actual,
    http: { ...actual.http, get: getMock, put: putMock, delete: deleteMock },
  }
})

import { useAuthSessionStore } from '@/features/auth/model/auth-session'

import { MessageFeedback } from './message-feedback'

const THREAD_ID = 't-1'
const MESSAGE_ID = 't-1:1'

const createClient = (): QueryClient =>
  new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })

const renderFeedback = (messageId: string = MESSAGE_ID) =>
  render(
    <QueryClientProvider client={createClient()}>
      <MessageFeedback messageId={messageId} threadId={THREAD_ID} />
    </QueryClientProvider>,
  )

const renderFeedbackWithoutMessageId = () =>
  render(
    <QueryClientProvider client={createClient()}>
      <MessageFeedback threadId={THREAD_ID} />
    </QueryClientProvider>,
  )

beforeEach(() => {
  getMock.mockResolvedValue([])
  putMock.mockResolvedValue({ messageId: MESSAGE_ID, rating: 'UP', reasonCode: null })
  deleteMock.mockResolvedValue(undefined)
  useAuthSessionStore.setState({
    status: 'authenticated',
    user: { publicId: 'user-1', username: 'tester', roles: ['USER'] },
  })
})

describe('MessageFeedback', () => {
  it('未登录时不渲染反馈入口', () => {
    useAuthSessionStore.setState({ status: 'unauthenticated', user: null })
    renderFeedback()
    expect(screen.queryByRole('button', { name: '回答有帮助' })).toBeNull()
  })

  it('缺少 message_id 时不渲染反馈入口', () => {
    renderFeedbackWithoutMessageId()
    expect(screen.queryByRole('button', { name: '回答有帮助' })).toBeNull()
  })

  it('点赞直接提交 UP，不展开踩面板', async () => {
    const user = userEvent.setup()
    renderFeedback()

    await user.click(screen.getByRole('button', { name: '回答有帮助' }))

    await waitFor(() =>
      expect(putMock).toHaveBeenCalledWith(`/messages/${MESSAGE_ID}/feedback`, {
        threadId: THREAD_ID,
        rating: 'UP',
      }),
    )
    expect(screen.queryByText('这条回答哪里有问题？')).toBeNull()
  })

  it('已有评价时恢复高亮，再次点赞即撤销', async () => {
    const user = userEvent.setup()
    getMock.mockResolvedValue([{ messageId: MESSAGE_ID, rating: 'UP', reasonCode: null }])
    renderFeedback()

    const upButton = screen.getByRole('button', { name: '回答有帮助' })
    await waitFor(() => expect(upButton).toHaveAttribute('aria-pressed', 'true'))

    await user.click(upButton)
    await waitFor(() => expect(deleteMock).toHaveBeenCalledWith(`/messages/${MESSAGE_ID}/feedback`))
  })

  it('踩需要选择原因并提交备注', async () => {
    const user = userEvent.setup()
    renderFeedback()

    await user.click(screen.getByRole('button', { name: '回答没帮助' }))
    await user.click(await screen.findByRole('button', { name: '答非所问' }))
    await user.type(screen.getByRole('textbox', { name: /补充说明/ }), '缺少关键参数')
    await user.click(screen.getByRole('button', { name: '提交' }))

    await waitFor(() =>
      expect(putMock).toHaveBeenCalledWith(`/messages/${MESSAGE_ID}/feedback`, {
        threadId: THREAD_ID,
        rating: 'DOWN',
        reasonCode: 'OFF_TOPIC',
        comment: '缺少关键参数',
      }),
    )
  })

  it('已踩时可在面板内移除反馈', async () => {
    const user = userEvent.setup()
    getMock.mockResolvedValue([
      { messageId: MESSAGE_ID, rating: 'DOWN', reasonCode: 'INACCURATE' },
    ])
    renderFeedback()

    const downButton = screen.getByRole('button', { name: '回答没帮助' })
    await waitFor(() => expect(downButton).toHaveAttribute('aria-pressed', 'true'))

    await user.click(downButton)
    await user.click(await screen.findByRole('button', { name: '移除反馈' }))

    await waitFor(() => expect(deleteMock).toHaveBeenCalledWith(`/messages/${MESSAGE_ID}/feedback`))
  })
})
