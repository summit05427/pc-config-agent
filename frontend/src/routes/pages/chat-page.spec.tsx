import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AgentRuntimeSnapshot, RuntimeMessage } from '@/features/chat/runtime/types'

import { ChatNewPage, ChatSessionPage } from './chat-page'

interface ChatSessionMock {
  threadId: string
  title: string
  messages: RuntimeMessage[]
  isLoadingHistory: boolean
  isPersisted: boolean
  isHistoryLoadError: boolean
  sessionModelKey: string | null
  refetchHistory: () => void
}

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  sessionId: 'thread-url',
  send: vi.fn(),
  stop: vi.fn(),
  retry: vi.fn(),
  regenerate: vi.fn(),
  setModel: vi.fn(),
  refetchHistory: vi.fn(),
  // 运行时快照由用例按需替换，页面只读当前值
  snapshot: {
    sessionId: null,
    messages: [],
    status: 'idle',
    isStreaming: false,
    error: null,
    canRetry: false,
    isRegenerating: false,
  } as AgentRuntimeSnapshot,
  session: {} as ChatSessionMock,
}))

// 页面只依赖路由参数与导航，替换掉需要 RouterContext 的真实实现
vi.mock('@tanstack/react-router', () => ({
  useParams: () => ({ sessionId: mocks.sessionId }),
  useNavigate: () => mocks.navigate,
}))

vi.mock('@/features/chat/hooks/use-agent-runtime', () => ({
  useAgentRuntime: () => ({
    runtime: null,
    snapshot: mocks.snapshot,
    send: mocks.send,
    stop: mocks.stop,
    retry: mocks.retry,
    regenerate: mocks.regenerate,
  }),
}))

vi.mock('@/features/chat/hooks/use-chat-session', () => ({
  useChatSession: () => mocks.session,
}))

vi.mock('@/features/chat/hooks/use-chat-model', () => ({
  useChatModel: () => ({
    models: [],
    isLoading: false,
    isAvailable: false,
    modelKey: 'openai:gpt',
    setModel: mocks.setModel,
  }),
}))

const createSnapshot = (overrides: Partial<AgentRuntimeSnapshot> = {}): AgentRuntimeSnapshot => ({
  sessionId: null,
  messages: [],
  status: 'idle',
  isStreaming: false,
  error: null,
  canRetry: false,
  isRegenerating: false,
  ...overrides,
})

const createAssistantMessage = (
  content: string,
  status: RuntimeMessage['status'] = 'streaming',
): RuntimeMessage => ({
  id: 'runtime-assistant',
  role: 'assistant',
  content,
  reasoning: '',
  steps: [],
  status,
  createdAt: 0,
})

const createUserMessage = (content: string): RuntimeMessage => ({
  id: 'runtime-user',
  role: 'user',
  content,
  reasoning: '',
  steps: [],
  status: 'done',
  createdAt: 0,
})

/** 提供 rerenderPage：页面依赖快照变化时用同一份 QueryClient 重新渲染整页 */
const renderPage = (page: ReactElement) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  const wrap = (next: ReactElement) => (
    <QueryClientProvider client={client}>{next}</QueryClientProvider>
  )
  const view = render(wrap(page))
  return {
    rerenderPage: (next: ReactElement): void => view.rerender(wrap(next)),
  }
}

beforeEach(() => {
  mocks.navigate.mockReset()
  mocks.send.mockReset()
  mocks.stop.mockReset()
  mocks.retry.mockReset()
  mocks.setModel.mockReset()
  mocks.refetchHistory.mockReset()
  mocks.snapshot = createSnapshot()
  mocks.session = {
    threadId: 'thread-1',
    title: '新对话',
    messages: [],
    isLoadingHistory: false,
    isPersisted: false,
    isHistoryLoadError: false,
    sessionModelKey: null,
    refetchHistory: mocks.refetchHistory,
  }
})

describe('ChatPage', () => {
  it('新建会话展示空态与默认标题', async () => {
    renderPage(<ChatNewPage />)

    expect(await screen.findByRole('heading', { level: 1, name: '新对话' })).toBeVisible()
    expect(await screen.findByRole('heading', { name: '开始一次任务' })).toBeVisible()
    expect(
      screen.getByText('Agent 的输出可能不准确，请在使用前核对关键信息。'),
    ).toBeVisible()
  })

  it('直接渲染会话模块给出的标题与服务端顺序消息', async () => {
    mocks.sessionId = 'thread-1'
    mocks.session = {
      ...mocks.session,
      title: '需求梳理',
      messages: [createUserMessage('历史问题'), createAssistantMessage('历史回答', 'done')],
    }
    renderPage(<ChatSessionPage />)

    expect(await screen.findByRole('heading', { level: 1, name: '需求梳理' })).toBeVisible()
    expect(await screen.findByText('历史回答')).toBeVisible()
    expect(screen.getByText('历史问题')).toBeVisible()
  })

  it('流式输出展示停止按钮，点击后中断生成', async () => {
    const user = userEvent.setup()
    mocks.sessionId = 'thread-1'
    mocks.snapshot = createSnapshot({
      status: 'streaming',
      isStreaming: true,
    })
    mocks.session = {
      ...mocks.session,
      title: '#thread-1',
      messages: [createAssistantMessage('正在生成的内容')],
    }
    renderPage(<ChatSessionPage />)

    // 尚无服务端标题时回退到短 ID，避免展示空白标题
    expect(screen.getByRole('heading', { level: 1, name: '#thread-1' })).toBeVisible()
    expect(screen.getAllByText('正在生成').length).toBeGreaterThan(0)
    // 流式尾块的字符被逐字 span 包裹，按整段 textContent 匹配
    expect(
      await screen.findByText(
        (_, element) => element?.tagName === 'P' && element.textContent === '正在生成的内容',
      ),
    ).toBeVisible()

    await user.click(screen.getByRole('button', { name: '停止生成' }))

    expect(mocks.stop).toHaveBeenCalledTimes(1)
  })

  it('发送消息时带上当前选中的模型', async () => {
    const user = userEvent.setup()
    mocks.sessionId = 'thread-1'
    renderPage(<ChatSessionPage />)

    await user.type(screen.getByLabelText('消息输入框'), '你好')
    await user.keyboard('{Enter}')

    expect(mocks.send).toHaveBeenCalledWith('你好', 'openai:gpt')
  })

  it('运行时错误保留已生成内容，错误条重试会带上模型重新发送', async () => {
    const user = userEvent.setup()
    mocks.sessionId = 'thread-1'
    mocks.snapshot = createSnapshot({
      status: 'error',
      messages: [createAssistantMessage('已生成部分内容', 'error')],
      error: {
        code: 'MODEL_FAILED',
        messageKey: 'chat.runtime.streamFailed',
        detail: '模型服务不可用',
        isRetryable: true,
      },
    })
    mocks.session = {
      ...mocks.session,
      messages: [createAssistantMessage('已生成部分内容', 'error')],
    }
    renderPage(<ChatSessionPage />)

    expect(await screen.findByText('已生成部分内容')).toBeVisible()
    const notice = await screen.findByRole('alert')
    expect(notice).toHaveTextContent('模型服务不可用')

    await user.click(within(notice).getByRole('button', { name: '重试' }))

    expect(mocks.retry).toHaveBeenCalledWith('openai:gpt')
  })

  it('历史加载失败展示错误条，重试会重新请求历史', async () => {
    const user = userEvent.setup()
    mocks.sessionId = 'thread-1'
    mocks.session = { ...mocks.session, isHistoryLoadError: true }
    renderPage(<ChatSessionPage />)

    const notice = await screen.findByRole('alert')
    expect(notice).toHaveTextContent('历史消息加载失败，请稍后重试。')

    await user.click(within(notice).getByRole('button', { name: '重试' }))

    expect(mocks.refetchHistory).toHaveBeenCalledTimes(1)
  })

  it('历史为空时展示空态，不展示错误条', async () => {
    mocks.sessionId = 'thread-1'
    mocks.session = { ...mocks.session, isHistoryLoadError: false }
    renderPage(<ChatSessionPage />)

    expect(await screen.findByRole('heading', { name: '开始一次任务' })).toBeVisible()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
