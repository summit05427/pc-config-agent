import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/features/sessions/api/request', () => ({
    sendAgentRequest: vi.fn(),
    INVALID_RESPONSE_MESSAGE: '响应解析失败',
}))

import { sendAgentRequest } from '@/features/sessions/api/request'
import { streamChat } from '@/features/sessions/api/stream-chat'
import type {
    ChatPreferences,
    ChatRequest,
    ChatStreamEvent,
    StreamChatOptions,
} from '@/features/sessions/api/types'

import { AgentRuntime } from './agent-runtime'
import type { AgentRuntimeDeps } from './types'

const SSE_HEADERS = { 'Content-Type': 'text/event-stream' }

const createSseResponse = (frames: string[]): Response => {
    const body = new ReadableStream<Uint8Array>({
        start(controller) {
            for (const frame of frames) {
                controller.enqueue(new TextEncoder().encode(frame))
            }
            controller.close()
        },
    })

    return new Response(body, { status: 200, headers: SSE_HEADERS })
}

interface Harness {
    runtime: AgentRuntime
    deps: AgentRuntimeDeps & {
        getPreferences: ReturnType<typeof vi.fn>
        confirmPersisted: ReturnType<typeof vi.fn>
        invalidateHistory: ReturnType<typeof vi.fn>
        invalidateSessions: ReturnType<typeof vi.fn>
        syncHistory: ReturnType<typeof vi.fn>
    }
}

const createHarness = (
    stream: AgentRuntimeDeps['stream'],
    preferences: ChatPreferences | null = null,
    scheduleFrame?: AgentRuntimeDeps['scheduleFrame'],
): Harness => {
    let sequence = 0
    const nextId = (): string => {
        sequence += 1
        return `id-${sequence}`
    }

    const deps = {
        stream,
        createId: vi.fn(nextId),
        now: vi.fn(() => 1000),
        getPreferences: vi.fn(async () => preferences),
        confirmPersisted: vi.fn(async () => undefined),
        invalidateHistory: vi.fn(async () => undefined),
        invalidateSessions: vi.fn(async () => undefined),
        syncHistory: vi.fn(async () => undefined),
        ...(scheduleFrame ? { scheduleFrame } : {}),
    }

    return { runtime: new AgentRuntime(deps), deps }
}

const findAssistant = (messages: ReturnType<AgentRuntime['getSnapshot']>['messages']) =>
    messages.find((message) => message.role === 'assistant')

const tokenFrame = (text: string): string => `event: token\ndata: ${JSON.stringify({ text })}\n\n`

beforeEach(() => {
    vi.mocked(sendAgentRequest).mockReset()
})

describe('AgentRuntime 流式事件', () => {
    it('按顺序消费五类事件，并把工具结果关联到对应调用', async () => {
        const { runtime } = createHarness(streamChat)
        vi.mocked(sendAgentRequest).mockResolvedValue(
            createSseResponse([
                tokenFrame('你'),
                tokenFrame('好'),
                'event: tool_call\ndata: {"name":"search","args":{"q":"x"}}\n\n',
                'event: tool_result\ndata: {"name":"search","preview":"结果 A"}\n\n',
                'event: done\ndata: {"thread_id":"thread-1"}\n\n',
            ]),
        )

        const snapshots: ReturnType<AgentRuntime['getSnapshot']>[] = []
        runtime.subscribe(() => snapshots.push(runtime.getSnapshot()))

        await runtime.send('问题')

        const doneSnapshot = snapshots.filter((item) => item.status === 'done').at(-1)
        const assistant = findAssistant(doneSnapshot?.messages ?? [])
        expect(doneSnapshot?.messages[0]?.role).toBe('user')
        expect(doneSnapshot?.messages[0]?.content).toBe('问题')
        expect(assistant?.content).toBe('你好')
        expect(assistant?.steps).toHaveLength(1)
        expect(assistant?.steps[0]?.name).toBe('search')
        expect(assistant?.steps[0]?.status).toBe('done')
        expect(assistant?.steps[0]?.result).toBe('结果 A')

        // 交接完成后临时状态被清空，历史由 Query 负责
        expect(runtime.getSnapshot()).toMatchObject({
            sessionId: 'thread-1',
            messages: [],
            status: 'idle',
        })
    })

    it('citations 事件把引用挂到当前助手消息，并按 sourceId 去重', async () => {
        const { runtime } = createHarness(streamChat)
        const citationFrame = (sourceId: string, score?: number): string =>
            `event: citations\ndata: ${JSON.stringify({
                citations: [
                    {
                        source_id: sourceId,
                        title: '官方规格表',
                        snippet: `${sourceId} 的说明`,
                        ...(score === undefined ? {} : { score }),
                    },
                ],
            })}\n\n`
        vi.mocked(sendAgentRequest).mockResolvedValue(
            createSseResponse([
                citationFrame('doc-1', 0.82),
                citationFrame('doc-1'),
                citationFrame('doc-2'),
                tokenFrame('回答'),
                'event: done\ndata: {"thread_id":"thread-1"}\n\n',
            ]),
        )

        const snapshots: ReturnType<AgentRuntime['getSnapshot']>[] = []
        runtime.subscribe(() => snapshots.push(runtime.getSnapshot()))

        await runtime.send('问题')

        const withCitations = snapshots
            .map((snapshot) => findAssistant(snapshot.messages))
            .filter((message) => (message?.citations?.length ?? 0) > 0)
            .at(-1)
        expect(withCitations?.citations?.map((item) => item.sourceId)).toEqual(['doc-1', 'doc-2'])
        expect(withCitations?.citations?.[0]?.score).toBeCloseTo(0.82)
    })

    it('done 携带 build_result 时挂到当前助手消息，畸形数据不阻断完成', async () => {
        const { runtime } = createHarness(streamChat)
        vi.mocked(sendAgentRequest).mockResolvedValue(
            createSseResponse([
                tokenFrame('配置如下'),
                'event: done\ndata: {"thread_id":"thread-1","build_result":{"components":[{"category":"CPU","model_name":"R7 7800X3D","price_fen":229900,"purchase_url":null,"benchmark":null,"offer_verified_at":null}],"total_price_fen":229900,"budget_max_fen":800000,"budget_status":"WITHIN_BUDGET","compatibility":[{"rule":"CPU 插槽","status":"PASS","message":"一致"}],"reason_summary":"均衡"}}\n\n',
            ]),
        )

        const snapshots: ReturnType<AgentRuntime['getSnapshot']>[] = []
        runtime.subscribe(() => snapshots.push(runtime.getSnapshot()))

        await runtime.send('配一台')

        const doneSnapshot = snapshots.filter((item) => item.status === 'done').at(-1)
        const assistant = findAssistant(doneSnapshot?.messages ?? [])
        expect(assistant?.buildResult?.components[0]?.modelName).toBe('R7 7800X3D')
        expect(assistant?.buildResult?.totalPriceFen).toBe(229900)
        expect(assistant?.buildResult?.overallCompatibility).toBe('PASS')
    })

    it('build_result 结构异常时按普通回答完成，不回填卡片', async () => {
        const { runtime } = createHarness(streamChat)
        vi.mocked(sendAgentRequest).mockResolvedValue(
            createSseResponse([
                tokenFrame('纯文本回答'),
                'event: done\ndata: {"thread_id":"thread-1","build_result":{"components":"bad"}}\n\n',
            ]),
        )

        const snapshots: ReturnType<AgentRuntime['getSnapshot']>[] = []
        runtime.subscribe(() => snapshots.push(runtime.getSnapshot()))

        await runtime.send('配一台')

        const doneSnapshot = snapshots.filter((item) => item.status === 'done').at(-1)
        const assistant = findAssistant(doneSnapshot?.messages ?? [])
        expect(assistant?.content).toBe('纯文本回答')
        expect(assistant?.buildResult).toBeUndefined()
    })

    it('思考内容与正文分开累积，不污染回答正文', async () => {
        const { runtime } = createHarness(streamChat)
        vi.mocked(sendAgentRequest).mockResolvedValue(
            createSseResponse([
                'event: reasoning\ndata: {"text":"先分析问题"}\n\n',
                tokenFrame('答案'),
                'event: done\ndata: {"thread_id":"thread-1"}\n\n',
            ]),
        )

        const snapshots: ReturnType<AgentRuntime['getSnapshot']>[] = []
        runtime.subscribe(() => snapshots.push(runtime.getSnapshot()))

        await runtime.send('问题')

        const streaming = snapshots.filter((item) => item.status === 'streaming').at(-1)
        const assistant = findAssistant(streaming?.messages ?? [])
        expect(assistant?.reasoning).toBe('先分析问题')
        expect(assistant?.content).toBe('答案')
    })

    it('未知事件被忽略且不中断后续帧', async () => {
        const { runtime } = createHarness(
            async function* () {
                yield { type: 'token', text: 'A' }
                yield { type: 'mystery', payload: 1 } as never
                yield { type: 'token', text: 'B' }
                yield { type: 'done', threadId: 'thread-2' }
            },
        )

        const snapshots: ReturnType<AgentRuntime['getSnapshot']>[] = []
        runtime.subscribe(() => snapshots.push(runtime.getSnapshot()))

        await runtime.send('问题')

        const doneSnapshot = snapshots.filter((item) => item.status === 'done').at(-1)
        expect(findAssistant(doneSnapshot?.messages ?? [])?.content).toBe('AB')
    })

    it('同一帧内的 token 合并发布，done 之前强制 flush', async () => {
        const scheduledFrames: Array<() => void> = []
        const scheduleFrame = vi.fn((callback: () => void) => {
            scheduledFrames.push(callback)
            return () => undefined
        })

        const { runtime } = createHarness(
            async function* () {
                for (let index = 0; index < 20; index += 1) {
                    yield { type: 'token', text: '字' }
                }
                yield { type: 'done', threadId: 'thread-batch' }
            },
            null,
            scheduleFrame,
        )

        const snapshots: ReturnType<AgentRuntime['getSnapshot']>[] = []
        runtime.subscribe(() => snapshots.push(runtime.getSnapshot()))

        await runtime.send('问题')

        // 20 个 token 只调度一次帧刷新，流式期间不应出现 20 次快照
        expect(scheduleFrame).toHaveBeenCalledTimes(1)
        expect(scheduledFrames).toHaveLength(1)

        const streamingWithContent = snapshots.filter(
            (item) =>
                item.status === 'streaming' &&
                findAssistant(item.messages)?.status === 'streaming' &&
                (findAssistant(item.messages)?.content.length ?? 0) > 0,
        )
        expect(streamingWithContent).toHaveLength(1)
        expect(findAssistant(streamingWithContent[0]?.messages ?? [])?.content).toBe(
            '字'.repeat(20),
        )
    })

    it('重新生成发送 regenerate 标记，并在流式期间标记 isRegenerating', async () => {
        let openGate: () => void = () => undefined
        const gate = new Promise<void>((resolve) => {
            openGate = resolve
        })
        const stream = vi.fn(
            async function* (
                _payload: ChatRequest,
                _options: StreamChatOptions,
            ): AsyncGenerator<ChatStreamEvent> {
                yield { type: 'token', text: '新回答' }
                await gate
                yield { type: 'done', threadId: 'thread-9' }
            },
        )
        const { runtime } = createHarness(stream)
        runtime.setSession('thread-9')

        const task = runtime.regenerate('上一个问题')

        expect(runtime.getSnapshot()).toMatchObject({
            status: 'streaming',
            isRegenerating: true,
        })
        await vi.waitFor(() => expect(stream).toHaveBeenCalled())
        expect(stream.mock.calls[0]?.[0]).toMatchObject({
            message: '上一个问题',
            regenerate: true,
        })

        openGate()
        await task

        expect(runtime.getSnapshot()).toMatchObject({
            status: 'idle',
            isRegenerating: false,
            messages: [],
        })
    })

    it('重复 send 只发起一次请求，且只有一条用户气泡', async () => {
        let openGate: () => void = () => undefined
        const gate = new Promise<void>((resolve) => {
            openGate = resolve
        })
        const stream: AgentRuntimeDeps['stream'] = async function* () {
            yield { type: 'token', text: 'A' }
            await gate
            yield { type: 'done', threadId: 'thread-3' }
        }
        const { runtime, deps } = createHarness(vi.fn(stream))

        const first = runtime.send('你好')
        const second = runtime.send('你好')
        await second

        expect(deps.stream).toHaveBeenCalledTimes(1)
        expect(
            runtime.getSnapshot().messages.filter((message) => message.role === 'user'),
        ).toHaveLength(1)

        openGate()
        await first
    })
})

describe('AgentRuntime 交接顺序', () => {
    it('done 之后才按「确认 → 失效 → 同步 → 清理 → 刷新列表」交接', async () => {
        const order: string[] = []
        let messageCountWhenRefreshingList = -1
        const { runtime, deps } = createHarness(streamChat)
        deps.confirmPersisted.mockImplementation(async () => {
            order.push('confirm')
        })
        deps.invalidateHistory.mockImplementation(async () => {
            order.push('invalidate')
        })
        deps.invalidateSessions.mockImplementation(async () => {
            order.push('invalidate-sessions')
            // 侧栏刷新必须晚于临时消息清理，否则列表插入与消息替换会同帧抖动
            messageCountWhenRefreshingList = runtime.getSnapshot().messages.length
        })
        deps.syncHistory.mockImplementation(async () => {
            order.push('sync')
        })
        vi.mocked(sendAgentRequest).mockResolvedValue(
            createSseResponse([tokenFrame('段'), 'event: done\ndata: {"thread_id":"thread-4"}\n\n']),
        )

        await runtime.send('问题')

        expect(order).toEqual(['confirm', 'invalidate', 'sync', 'invalidate-sessions'])
        expect(messageCountWhenRefreshingList).toBe(0)
        expect(deps.confirmPersisted).toHaveBeenCalledWith('thread-4')
        expect(deps.invalidateHistory).toHaveBeenCalledWith('thread-4')
        expect(deps.syncHistory).toHaveBeenCalledWith('thread-4')
        expect(runtime.getSnapshot().messages).toEqual([])
    })

    it('失败路径不触发 invalidate', async () => {
        const { runtime, deps } = createHarness(streamChat)
        vi.mocked(sendAgentRequest).mockResolvedValue(
            createSseResponse([
                'event: error\ndata: {"code":"upstream","message":"模型不可用"}\n\n',
            ]),
        )

        await runtime.send('问题')

        expect(deps.invalidateHistory).not.toHaveBeenCalled()
        expect(deps.syncHistory).not.toHaveBeenCalled()
    })

    it('交接等待确认期间切换会话时旧交接不再继续', async () => {
        let resolveConfirm: () => void = () => undefined
        const confirmGate = new Promise<void>((resolve) => {
            resolveConfirm = resolve
        })
        const { runtime, deps } = createHarness(streamChat)
        deps.confirmPersisted.mockImplementation(async () => {
            await confirmGate
        })
        vi.mocked(sendAgentRequest).mockResolvedValue(
            createSseResponse([tokenFrame('答'), 'event: done\ndata: {"thread_id":"thread-5"}\n\n']),
        )

        const sendPromise = runtime.send('问题')
        await vi.waitFor(() => expect(deps.confirmPersisted).toHaveBeenCalledWith('thread-5'))

        // 会话切换会让运行序号归零，确认返回后立即终止旧交接
        runtime.setSession('thread-b')
        resolveConfirm()
        await sendPromise

        expect(deps.invalidateHistory).not.toHaveBeenCalled()
        expect(deps.syncHistory).not.toHaveBeenCalled()
        expect(runtime.getSnapshot()).toMatchObject({ sessionId: 'thread-b', messages: [] })
    })
})

describe('AgentRuntime HITL 中断与恢复', () => {
    const interruptEvent = (): ChatStreamEvent => ({
        type: 'interrupt',
        interrupt: {
            interruptId: 'int-1',
            interactionType: 'clarify_requirements',
            question: '还缺预算',
            fields: [
                { name: 'budget_yuan', label: '预算', type: 'number', required: true, min: 1000 },
            ],
            submitLabel: '继续',
            context: { missing_slots: ['budget_yuan'] },
        },
    })

    it('interrupt 作为本轮终态：进入 awaiting_input，不判失败也不交接', async () => {
        const { runtime, deps } = createHarness(async function* () {
            yield { type: 'token', text: '请补充预算' }
            yield interruptEvent()
        })
        runtime.setSession('thread-hitl')

        await runtime.send('配一台电脑')

        expect(runtime.getSnapshot()).toMatchObject({
            status: 'awaiting_input',
            isStreaming: false,
            canRetry: false,
            error: null,
        })
        const assistant = findAssistant(runtime.getSnapshot().messages)
        expect(assistant?.status).toBe('awaiting_input')
        expect(assistant?.hitl?.interruptId).toBe('int-1')
        // 中断保留临时消息等待用户回答，不能按 stream_incomplete 判失败
        expect(runtime.getSnapshot().messages).toHaveLength(2)
        expect(deps.invalidateHistory).not.toHaveBeenCalled()
    })

    it('resume 携带 interrupt_id 与结构化答案，回答文本进入用户气泡', async () => {
        const streams: ChatStreamEvent[][] = [
            [interruptEvent()],
            [{ type: 'done', threadId: 'thread-hitl' }],
        ]
        let callIndex = 0
        const stream = vi.fn(
            async function* (
                _payload: ChatRequest,
                _options: StreamChatOptions,
            ): AsyncGenerator<ChatStreamEvent> {
                const events = streams[callIndex] ?? []
                callIndex += 1
                for (const event of events) {
                    yield event
                }
            },
        )
        const { runtime } = createHarness(stream)
        runtime.setSession('thread-hitl')

        await runtime.send('配一台电脑')
        const interrupt = findAssistant(runtime.getSnapshot().messages)?.hitl
        if (!interrupt) {
            throw new Error('expected interrupt payload')
        }

        await runtime.resume('预算：8000 元', interrupt, { budget_yuan: 8000 })

        expect(stream.mock.calls[1]?.[0]).toMatchObject({
            message: '预算：8000 元',
            thread_id: 'thread-hitl',
            resume: { interrupt_id: 'int-1', answer: { budget_yuan: 8000 } },
        })
        expect(runtime.getSnapshot()).toMatchObject({ status: 'idle', messages: [] })
    })
})

describe('AgentRuntime 偏好下发', () => {
    const readRequestBody = (): { preferences?: unknown } =>
        JSON.parse(String(vi.mocked(sendAgentRequest).mock.calls[0]?.[1]?.body ?? '{}')) as {
            preferences?: unknown
        }

    it('每轮请求都携带偏好（Agent 只从请求体读取，不查库）', async () => {
        const preferences = {
            instructions: '回答要简洁',
            reply_language: 'zh-CN',
            response_style: 'concise',
            use_history: false,
        } as const
        const { runtime, deps } = createHarness(streamChat, preferences)
        vi.mocked(sendAgentRequest).mockResolvedValue(
            createSseResponse(['event: done\ndata: {"thread_id":"thread-6"}\n\n']),
        )

        await runtime.send('问题')

        expect(deps.getPreferences).toHaveBeenCalledTimes(1)
        expect(readRequestBody().preferences).toEqual(preferences)
    })

    it('偏好不可用时请求体不带 preferences，对话照常发起', async () => {
        const { runtime, deps } = createHarness(streamChat, null)
        vi.mocked(sendAgentRequest).mockResolvedValue(
            createSseResponse(['event: done\ndata: {"thread_id":"thread-7"}\n\n']),
        )

        await runtime.send('问题')

        expect(deps.getPreferences).toHaveBeenCalledTimes(1)
        expect(readRequestBody().preferences).toBeUndefined()
        expect(runtime.getSnapshot().messages).toEqual([])
    })
})
