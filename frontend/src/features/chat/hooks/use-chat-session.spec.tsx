import { StrictMode, type ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/features/sessions/api/request', () => ({
    sendAgentRequest: vi.fn(),
    requestAgentJson: vi.fn(),
    requestAgentVoid: vi.fn(),
    buildAgentUrl: vi.fn(),
    INVALID_RESPONSE_MESSAGE: '响应解析失败',
}))

import { STORAGE_KEYS } from '@/constants/storage'
import { ApiError } from '@/core/http'
import { AgentRuntime } from '@/features/chat/runtime/agent-runtime'
import { clearDraftThread, markDraftThread } from '@/features/chat/runtime/agent-thread'
import type { AgentRuntimeDeps } from '@/features/chat/runtime/types'
import { requestAgentJson } from '@/features/sessions/api/request'

import { useChatSession } from './use-chat-session'

const EMPTY_PAGE = { list: [], total: 0, page: 1, size: 100, thread_id: 'thread' }

/** 历史与会话列表可能并发请求，按路径返回，避免依赖调用顺序 */
const mockResponses = (handler: (path: string) => Promise<unknown>): void => {
    vi.mocked(requestAgentJson).mockImplementation(
        handler as unknown as typeof requestAgentJson,
    )
}

const requestedMessages = (): boolean =>
    vi.mocked(requestAgentJson).mock.calls.some(([path]) => String(path).endsWith('/messages'))

const createRuntime = (
    stream: AgentRuntimeDeps['stream'] = async function* () {},
): AgentRuntime =>
    new AgentRuntime({
        stream,
        createId: () => 'runtime-generated',
        now: () => 1000,
        getPreferences: async () => null,
        confirmPersisted: async () => undefined,
        invalidateHistory: async () => undefined,
        invalidateSessions: async () => undefined,
        syncHistory: async () => undefined,
    })

const createClient = (): QueryClient =>
    new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })

const createWrapper = (client: QueryClient, useStrictMode = false) => {
    const Wrapper = ({ children }: { children: ReactNode }) => {
        const tree = <QueryClientProvider client={client}>{children}</QueryClientProvider>
        return useStrictMode ? <StrictMode>{tree}</StrictMode> : tree
    }
    return Wrapper
}

const readMirror = (): unknown =>
    JSON.parse(window.sessionStorage.getItem(STORAGE_KEYS.agentThread) ?? 'null') as unknown

beforeEach(() => {
    window.sessionStorage.clear()
    vi.mocked(requestAgentJson).mockReset()
    vi.mocked(requestAgentJson).mockResolvedValue(EMPTY_PAGE)
})

describe('useChatSession', () => {
    it('URL 中的会话 ID 优先于镜像，并直接绑定到运行时', async () => {
        window.sessionStorage.setItem(STORAGE_KEYS.agentThread, JSON.stringify('thread-mirror'))
        const runtime = createRuntime()
        const setSession = vi.spyOn(runtime, 'setSession')
        const onCanonicalize = vi.fn()

        const { result } = renderHook(
            () =>
                useChatSession({
                    sessionId: 'thread-url',
                    isNewSession: false,
                    runtime,
                    snapshot: runtime.getSnapshot(),
                    onCanonicalize,
                    untitledLabel: '新对话',
                }),
            { wrapper: createWrapper(createClient()) },
        )

        expect(result.current.threadId).toBe('thread-url')
        await waitFor(() => expect(result.current.isLoadingHistory).toBe(false))
        expect(setSession).toHaveBeenCalledWith('thread-url')
        expect(onCanonicalize).not.toHaveBeenCalled()
        expect(readMirror()).toBe('thread-url')
        expect(requestAgentJson).toHaveBeenCalledWith(
            '/sessions/thread-url/messages',
            { method: 'GET' },
            { page: 1, size: 100, order: 'desc' },
        )
    })

    it('/chat/new 每次生成新会话，StrictMode 下只规范化与切换一次', async () => {
        const runtime = createRuntime()
        const setSession = vi.spyOn(runtime, 'setSession')
        const onCanonicalize = vi.fn()

        const { result } = renderHook(
            () =>
                useChatSession({
                    sessionId: undefined,
                    isNewSession: true,
                    runtime,
                    snapshot: runtime.getSnapshot(),
                    onCanonicalize,
                    untitledLabel: '新对话',
                }),
            { wrapper: createWrapper(createClient(), true) },
        )

        await waitFor(() => expect(result.current.isLoadingHistory).toBe(false))
        expect(onCanonicalize).toHaveBeenCalledTimes(1)
        expect(onCanonicalize).toHaveBeenCalledWith(result.current.threadId)
        expect(setSession).toHaveBeenCalledTimes(1)
        expect(setSession).toHaveBeenCalledWith(result.current.threadId)
        expect(readMirror()).toBe(result.current.threadId)
        // 草稿尚未落库，不能查询历史，否则必然 404 并闪出骨架屏
        expect(result.current.isPersisted).toBe(false)
        expect(requestedMessages()).toBe(false)
    })

    it('URL 缺失时回退镜像并立即转成规范 URL', async () => {
        window.sessionStorage.setItem(STORAGE_KEYS.agentThread, JSON.stringify('thread-mirror'))
        const runtime = createRuntime()
        const setSession = vi.spyOn(runtime, 'setSession')
        const onCanonicalize = vi.fn()

        const { result } = renderHook(
            () =>
                useChatSession({
                    sessionId: undefined,
                    isNewSession: false,
                    runtime,
                    snapshot: runtime.getSnapshot(),
                    onCanonicalize,
                    untitledLabel: '新对话',
                }),
            { wrapper: createWrapper(createClient()) },
        )

        expect(result.current.threadId).toBe('thread-mirror')
        await waitFor(() => expect(result.current.isLoadingHistory).toBe(false))
        expect(onCanonicalize).toHaveBeenCalledWith('thread-mirror')
        expect(setSession).toHaveBeenCalledWith('thread-mirror')
    })

    it('切换会话会 abort 在途流并清空运行时临时消息', async () => {
        let release: () => void = () => undefined
        const gate = new Promise<void>((resolve) => {
            release = resolve
        })
        let capturedSignal: AbortSignal | undefined
        const runtime = createRuntime(async function* (_payload, options) {
            capturedSignal = options.signal
            yield { type: 'token', text: '片段' }
            await gate
            yield { type: 'token', text: '后续' }
        })
        const onCanonicalize = vi.fn()

        const { result, rerender } = renderHook(
            ({ sessionId }: { sessionId: string }) =>
                useChatSession({
                    sessionId,
                    isNewSession: false,
                    runtime,
                    snapshot: runtime.getSnapshot(),
                    onCanonicalize,
                    untitledLabel: '新对话',
                }),
            { wrapper: createWrapper(createClient()), initialProps: { sessionId: 'thread-a' } },
        )

        expect(result.current.threadId).toBe('thread-a')

        const sendPromise = runtime.send('问题')
        await vi.waitFor(() => expect(capturedSignal).toBeDefined())

        rerender({ sessionId: 'thread-b' })

        await waitFor(() => expect(capturedSignal?.aborted).toBe(true))
        expect(runtime.getSnapshot()).toMatchObject({ sessionId: 'thread-b', messages: [] })

        release()
        await sendPromise

        expect(runtime.getSnapshot()).toMatchObject({ sessionId: 'thread-b', messages: [] })
    })

    it('从同一份会话列表取标题、模型与落库状态，并按时间正序合并历史', async () => {
        const runtime = createRuntime()
        mockResponses(async (path) =>
            path.endsWith('/messages')
                ? {
                      thread_id: 'thread-1',
                      list: [
                          { role: 'assistant', content: '历史回答' },
                          { role: 'user', content: '历史问题' },
                      ],
                      total: 2,
                      page: 1,
                      size: 100,
                  }
                : {
                      list: [
                          { thread_id: 'thread-1', title: '需求梳理', model_key: 'openai:gpt-4o' },
                      ],
                      total: 1,
                      page: 1,
                      size: 20,
                  },
        )

        const { result } = renderHook(
            () =>
                useChatSession({
                    sessionId: 'thread-1',
                    isNewSession: false,
                    runtime,
                    snapshot: runtime.getSnapshot(),
                    onCanonicalize: vi.fn(),
                    untitledLabel: '新对话',
                }),
            { wrapper: createWrapper(createClient()) },
        )

        await waitFor(() => expect(result.current.isLoadingHistory).toBe(false))
        await waitFor(() => expect(result.current.title).toBe('需求梳理'))

        expect(result.current.sessionModelKey).toBe('openai:gpt-4o')
        expect(result.current.messages.map((message) => message.content)).toEqual([
            '历史问题',
            '历史回答',
        ])
        expect(requestAgentJson).toHaveBeenCalledWith(
            '/sessions',
            { method: 'GET' },
            { page: 1, size: 20, archived: 'false' },
        )
    })

    it('历史 500 与 404 都标记加载失败，不再把 404 当作空会话', async () => {
        const runtime = createRuntime()
        let status = 500

        mockResponses(async (path) => {
            if (path.endsWith('/messages')) {
                throw new ApiError('failed', { status })
            }
            return EMPTY_PAGE
        })

        const { result, rerender } = renderHook(
            ({ threadId }: { threadId: string }) =>
                useChatSession({
                    sessionId: threadId,
                    isNewSession: false,
                    runtime,
                    snapshot: runtime.getSnapshot(),
                    onCanonicalize: vi.fn(),
                    untitledLabel: '新对话',
                }),
            { wrapper: createWrapper(createClient()), initialProps: { threadId: 'thread-1' } },
        )

        await waitFor(() => expect(result.current.isHistoryLoadError).toBe(true))

        status = 404
        rerender({ threadId: 'thread-2' })

        await waitFor(() => expect(result.current.isLoadingHistory).toBe(false))
        expect(result.current.isHistoryLoadError).toBe(true)
        expect(result.current.isPersisted).toBe(false)
    })

    it('草稿会话不查询历史，落库确认后恢复查询', async () => {
        markDraftThread('thread-draft')
        const runtime = createRuntime()

        const { result, rerender } = renderHook(
            ({ threadId }: { threadId: string }) =>
                useChatSession({
                    sessionId: threadId,
                    isNewSession: false,
                    runtime,
                    snapshot: runtime.getSnapshot(),
                    onCanonicalize: vi.fn(),
                    untitledLabel: '新对话',
                }),
            { wrapper: createWrapper(createClient()), initialProps: { threadId: 'thread-draft' } },
        )

        expect(result.current.isLoadingHistory).toBe(false)
        expect(result.current.isPersisted).toBe(false)
        expect(requestedMessages()).toBe(false)

        clearDraftThread('thread-draft')
        rerender({ threadId: 'thread-draft' })

        await waitFor(() => expect(requestedMessages()).toBe(true))
        await waitFor(() => expect(result.current.isLoadingHistory).toBe(false))
    })

    it('运行时绑定当前会话后，done 带回的真实 ID 才写成规范地址', async () => {
        const runtime = createRuntime()
        const onCanonicalize = vi.fn()
        const baseSnapshot = runtime.getSnapshot()

        const { rerender } = renderHook(
            ({ snapshot }: { snapshot: typeof baseSnapshot }) =>
                useChatSession({
                    sessionId: 'thread-1',
                    isNewSession: false,
                    runtime,
                    snapshot,
                    onCanonicalize,
                    untitledLabel: '新对话',
                }),
            {
                wrapper: createWrapper(createClient()),
                initialProps: {
                    snapshot: { ...baseSnapshot, sessionId: 'thread-1', status: 'idle' },
                },
            },
        )

        rerender({ snapshot: { ...baseSnapshot, sessionId: 'thread-resolved', status: 'idle' } })

        await waitFor(() => expect(onCanonicalize).toHaveBeenCalledWith('thread-resolved'))
    })

    it('快照里残留的其它会话 ID 不会改写当前地址', async () => {
        const runtime = createRuntime()
        const onCanonicalize = vi.fn()
        const baseSnapshot = runtime.getSnapshot()

        const { result } = renderHook(
            () =>
                useChatSession({
                    sessionId: 'thread-b',
                    isNewSession: false,
                    runtime,
                    snapshot: { ...baseSnapshot, sessionId: 'thread-a', status: 'idle' },
                    onCanonicalize,
                    untitledLabel: '新对话',
                }),
            { wrapper: createWrapper(createClient()) },
        )

        await waitFor(() => expect(result.current.isLoadingHistory).toBe(false))
        expect(onCanonicalize).not.toHaveBeenCalled()
    })
})
