import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/features/sessions/api/request', () => ({
    sendAgentRequest: vi.fn(),
    INVALID_RESPONSE_MESSAGE: '响应解析失败',
}))

import { ApiError } from '@/core/http'
import { sendAgentRequest } from '@/features/sessions/api/request'
import { streamChat } from '@/features/sessions/api/stream-chat'

import { AgentRuntime } from './agent-runtime'
import type { AgentRuntimeDeps } from './types'

const SSE_HEADERS = { 'Content-Type': 'text/event-stream' }

interface ManualStream {
    readonly response: Response
    push: (frame: string) => void
    fail: (error: unknown) => void
}

const createManualStream = (): ManualStream => {
    let streamController: ReadableStreamDefaultController<Uint8Array> | null = null
    const body = new ReadableStream<Uint8Array>({
        start(controller) {
            streamController = controller
        },
    })
    const encoder = new TextEncoder()

    return {
        response: new Response(body, { status: 200, headers: SSE_HEADERS }),
        push: (frame) => streamController?.enqueue(encoder.encode(frame)),
        fail: (error) => streamController?.error(error),
    }
}

const createHarness = (stream: AgentRuntimeDeps['stream']) => {
    let sequence = 0
    const nextId = (): string => {
        sequence += 1
        return `id-${sequence}`
    }
    const deps = {
        stream,
        createId: vi.fn(nextId),
        now: vi.fn(() => 1000),
        getPreferences: vi.fn(async () => null),
        confirmPersisted: vi.fn(async () => undefined),
        invalidateHistory: vi.fn(async () => undefined),
        invalidateSessions: vi.fn(async () => undefined),
        syncHistory: vi.fn(async () => undefined),
    }
    return { runtime: new AgentRuntime(deps), deps }
}

const assistantContent = (runtime: AgentRuntime): string =>
    runtime.getSnapshot().messages.find((message) => message.role === 'assistant')?.content ?? ''

const tokenFrame = (text: string): string => `event: token\ndata: ${JSON.stringify({ text })}\n\n`

beforeEach(() => {
    vi.mocked(sendAgentRequest).mockReset()
})

describe('AgentRuntime 失败与中断', () => {
    it('error 事件保留已生成内容并给出可重试状态', async () => {
        const { runtime, deps } = createHarness(streamChat)
        vi.mocked(sendAgentRequest).mockResolvedValue(
            new Response(
                new ReadableStream<Uint8Array>({
                    start(controller) {
                        controller.enqueue(
                            new TextEncoder().encode(
                                `${tokenFrame('半句')}event: error\ndata: {"code":"upstream","message":"模型不可用"}\n\n`,
                            ),
                        )
                        controller.close()
                    },
                }),
                { status: 200, headers: SSE_HEADERS },
            ),
        )

        await runtime.send('问题')

        expect(assistantContent(runtime)).toBe('半句')
        expect(runtime.getSnapshot()).toMatchObject({
            status: 'error',
            canRetry: true,
            error: { code: 'upstream', messageKey: 'chat.runtime.streamFailed' },
        })
        expect(deps.invalidateHistory).not.toHaveBeenCalled()
    })

    it('HTTP 非 200 在建立流前失败时保留用户消息并可重试', async () => {
        const { runtime } = createHarness(streamChat)
        vi.mocked(sendAgentRequest).mockRejectedValue(
            new ApiError('服务器内部错误', { status: 500 }),
        )

        await runtime.send('问题')

        expect(runtime.getSnapshot().messages).toHaveLength(2)
        expect(runtime.getSnapshot()).toMatchObject({
            status: 'error',
            canRetry: true,
            error: { messageKey: 'chat.runtime.requestFailed' },
        })
    })

    it('流中途网络中断时保留已生成内容', async () => {
        const manual = createManualStream()
        const { runtime } = createHarness(streamChat)
        vi.mocked(sendAgentRequest).mockResolvedValue(manual.response)

        const sendPromise = runtime.send('问题')
        manual.push(tokenFrame('第一段'))
        await vi.waitFor(() => expect(assistantContent(runtime)).toBe('第一段'))
        manual.fail(new TypeError('network error'))

        await sendPromise

        expect(assistantContent(runtime)).toBe('第一段')
        expect(runtime.getSnapshot()).toMatchObject({
            status: 'error',
            canRetry: true,
            error: { messageKey: 'chat.runtime.interrupted' },
        })
    })

    it('停止生成后不再追加 token，并保留已有内容', async () => {
        const manual = createManualStream()
        const { runtime, deps } = createHarness(streamChat)
        vi.mocked(sendAgentRequest).mockResolvedValue(manual.response)

        const sendPromise = runtime.send('问题')
        manual.push(tokenFrame('第一段'))
        await vi.waitFor(() => expect(assistantContent(runtime)).toBe('第一段'))

        runtime.stop()
        manual.push(tokenFrame('第二段'))
        await sendPromise

        expect(assistantContent(runtime)).toBe('第一段')
        expect(runtime.getSnapshot().status).toBe('cancelled')
        expect(runtime.getSnapshot().canRetry).toBe(true)
        expect(deps.invalidateHistory).not.toHaveBeenCalled()
    })

    it('交接失败时保留已生成内容并标记同步失败', async () => {
        const { runtime, deps } = createHarness(streamChat)
        deps.syncHistory.mockRejectedValue(new ApiError('同步失败', { status: 500 }))
        vi.mocked(sendAgentRequest).mockResolvedValue(
            new Response(
                new ReadableStream<Uint8Array>({
                    start(controller) {
                        controller.enqueue(
                            new TextEncoder().encode(
                                `${tokenFrame('完整回答')}event: done\ndata: {"thread_id":"thread-9"}\n\n`,
                            ),
                        )
                        controller.close()
                    },
                }),
                { status: 200, headers: SSE_HEADERS },
            ),
        )

        await runtime.send('问题')

        expect(assistantContent(runtime)).toBe('完整回答')
        expect(runtime.getSnapshot()).toMatchObject({
            status: 'error',
            canRetry: true,
            error: { messageKey: 'chat.runtime.syncFailed' },
        })
    })
})

describe('AgentRuntime 会话与重试', () => {
    it('切换会话会 abort 在途流并清空临时状态', async () => {
        let openGate: () => void = () => undefined
        const gate = new Promise<void>((resolve) => {
            openGate = resolve
        })
        let capturedSignal: AbortSignal | undefined
        const { runtime } = createHarness(async function* (_payload, options) {
            capturedSignal = options.signal
            yield { type: 'token', text: '第一段' }
            await gate
            yield { type: 'token', text: '第二段' }
        })

        const sendPromise = runtime.send('问题')
        await vi.waitFor(() => expect(capturedSignal).toBeDefined())

        runtime.setSession('thread-b')
        expect(capturedSignal?.aborted).toBe(true)
        expect(runtime.getSnapshot()).toMatchObject({ sessionId: 'thread-b', messages: [] })

        openGate()
        await sendPromise
        expect(runtime.getSnapshot().messages).toEqual([])
    })

    it('重试复用原用户消息，只替换失败的回答', async () => {
        let round = 0
        const { runtime } = createHarness(async function* () {
            round += 1
            if (round === 1) {
                yield { type: 'error', code: 'upstream', message: '第一轮失败' }
                return
            }
            yield { type: 'token', text: '第二版回答' }
        })

        await runtime.send('同一个问题')
        await runtime.retry()

        const snapshot = runtime.getSnapshot()
        expect(snapshot.messages.filter((message) => message.role === 'user')).toHaveLength(1)
        expect(snapshot.messages[0]?.content).toBe('同一个问题')
        expect(assistantContent(runtime)).toBe('第二版回答')
        expect(snapshot.status).toBe('error')
    })

    it('setSession 在同一会话且空闲时不打断状态', async () => {
        const { runtime } = createHarness(async function* () {
            yield { type: 'done', threadId: 'thread-c' }
        })
        runtime.setSession('thread-c')
        const before = runtime.getSnapshot()
        runtime.setSession('thread-c')

        expect(runtime.getSnapshot()).toBe(before)
    })
})
