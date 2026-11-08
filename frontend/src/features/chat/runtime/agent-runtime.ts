import { normalizeError } from '@/core/http'
import type { ChatStreamEvent } from '@/features/sessions/api'

import {
    appendReasoning,
    appendToken,
    appendToolStep,
    attachToolResult,
    buildTurnMessages,
    createToolStep,
    finalizeSteps,
    findLastByRole,
    updateMessage,
} from './message-model'
import { handoffTurn } from './turn-handoff'
import type { AgentRuntimeDeps, AgentRuntimeSnapshot, RuntimeMessage } from './types'

/** 错误文案统一走 i18n key，运行时本身不持有任何一种语言的字符串 */
const MESSAGE_KEYS = {
    stream: 'chat.runtime.streamFailed',
    request: 'chat.runtime.requestFailed',
    interrupted: 'chat.runtime.interrupted',
    sync: 'chat.runtime.syncFailed',
} as const

const INCOMPLETE_CODE = 'stream_incomplete'

/** 非浏览器环境（无 rAF）的退化刷新间隔，防止缓冲无限期滞留 */
const FLUSH_FALLBACK_MS = 16

/**
 * 默认帧调度。
 *
 * SSE 一秒可能推送数百个 token，逐条 `publish` 会把主线程切成大量同步渲染；
 * 合并到每帧一次既保留逐字观感，又把渲染预算固定在 60fps 以内。
 */
const scheduleAnimationFrame = (callback: () => void): (() => void) => {
    if (typeof requestAnimationFrame === 'function') {
        const handle = requestAnimationFrame(callback)
        return () => cancelAnimationFrame(handle)
    }

    const handle = setTimeout(callback, FLUSH_FALLBACK_MS)
    return () => clearTimeout(handle)
}

interface ActiveTurn {
    readonly threadId: string
    readonly assistantId: string
    /** done 或 error 之后置位，后续迟到的事件一律忽略 */
    isClosed: boolean
}

/** 运行时没有临时消息时的基线快照；会话切换与交接完成后都回到这里 */
const createEmptySnapshot = (sessionId: string | null): AgentRuntimeSnapshot => ({
    sessionId,
    messages: [],
    status: 'idle',
    isStreaming: false,
    error: null,
    canRetry: false,
    isRegenerating: false,
})

const createUserId = (turnId: string): string => `user:${turnId}`

const createAssistantId = (turnId: string): string => `assistant:${turnId}`

const createStepId = (assistantId: string, index: number): string =>
    `${assistantId}:step:${index}`

const isAbortError = (error: unknown): boolean =>
    error instanceof Error && error.name === 'AbortError'

const toErrorCode = (error: unknown): string => String(normalizeError(error).code)

const describeError = (error: unknown): string => normalizeError(error).message

/**
 * Agent 运行时：流式对话的唯一临时状态源与单轮状态机。
 *
 * 不进入 Zustand、不进入 Query Cache，只通过 `subscribe/getSnapshot` 暴露给组件层。
 * 订阅、幂等守卫、流事件处理与交接编排都在这里，避免状态机与快照壳分居两处；
 * 消息在 `done` 之后才交接给 Query，顺序固定为
 * 「持久化确认 → invalidate → 历史重新同步 → 清理临时状态」。
 */
export class AgentRuntime {
    private snapshot: AgentRuntimeSnapshot = createEmptySnapshot(null)

    private readonly listeners = new Set<() => void>()

    private readonly deps: AgentRuntimeDeps

    private controller: AbortController | null = null
    private turn: ActiveTurn | null = null
    /** 当前有效的运行序号；取消后归零，让旧流的回调全部失效 */
    private activeRunId = 0
    private nextRunId = 0
    private isStopRequested = false

    /** 尚未发布到快照的流式文本；每帧最多写回一次 */
    private pendingContent = ''
    private pendingReasoning = ''
    private cancelScheduledFlush: (() => void) | null = null

    constructor(deps: AgentRuntimeDeps) {
        this.deps = deps
    }

    /** 箭头函数保证引用稳定，可直接传给 useSyncExternalStore */
    readonly subscribe = (listener: () => void): (() => void) => {
        this.listeners.add(listener)
        return () => {
            this.listeners.delete(listener)
        }
    }

    readonly getSnapshot = (): AgentRuntimeSnapshot => this.snapshot

    /**
     * 绑定当前会话。
     *
     * URL 是会话的唯一权威来源；切换会话必须中止在途流并清空临时消息，
     * 否则新会话会短暂显示上一个会话的流式内容。
     */
    setSession(sessionId: string | null): void {
        if (this.snapshot.sessionId === sessionId && this.snapshot.status !== 'streaming') {
            return
        }

        this.cancelRun()
        this.publish(createEmptySnapshot(sessionId))
    }

    /**
     * 发起一轮对话。
     *
     * 实例级幂等 guard：状态在第一个 await 之前就切换为 streaming，
     * 双击、StrictMode 重复调用都只会产生一个请求。
     */
    async send(text: string, model?: string | null): Promise<void> {
        const content = text.trim()
        if (!content || this.snapshot.status === 'streaming') {
            return
        }

        await this.runTurn(content, false, model)
    }

    /**
     * 重新生成最后一条回答。
     *
     * 服务端按 `regenerate=true` 移除最后一条 AI 消息后重跑模型；
     * 前端在流式期间隐藏历史里的最后一组提问与回答，由本次临时消息占位。
     */
    async regenerate(content: string, model?: string | null): Promise<void> {
        const trimmed = content.trim()
        if (!trimmed || this.snapshot.status === 'streaming' || !this.snapshot.sessionId) {
            return
        }

        await this.runTurn(trimmed, false, model, true)
    }

    /** 重试最近一次提问：复用原用户消息，只替换失败的回答气泡 */
    async retry(model?: string | null): Promise<void> {
        if (!this.snapshot.canRetry || this.snapshot.status === 'streaming') {
            return
        }

        const lastUser = findLastByRole(this.snapshot.messages, 'user')
        if (!lastUser) {
            return
        }

        await this.runTurn(lastUser.content, true, model)
    }

    /** 停止生成：先把缓冲写回，再中止流；已生成内容不丢失 */
    stop(): void {
        if (this.snapshot.status !== 'streaming') {
            return
        }

        this.flushPending()
        this.isStopRequested = true
        this.controller?.abort()
    }

    /**
     * 发起一轮生成。
     *
     * `send/retry` 已在第一个 await 之前切换为 streaming，因此这里天然具备实例级幂等。
     */
    private async runTurn(
        content: string,
        isRetry: boolean,
        model?: string | null,
        isRegenerate = false,
    ): Promise<void> {
        const threadId = this.snapshot.sessionId ?? this.deps.createId()
        const runId = this.beginRun(threadId, content, isRetry, isRegenerate)
        const controller = new AbortController()
        this.controller = controller
        this.isStopRequested = false

        try {
            // Agent 只从请求体读取偏好，不查库：每轮必须取一次，取不到就不携带
            const preferences = await this.deps.getPreferences()
            // 单轮显式模型优先于会话默认，用户切换后紧接着发送也能生效
            const stream = this.deps.stream(
                {
                    message: content,
                    thread_id: threadId,
                    model: model ?? undefined,
                    preferences: preferences ?? undefined,
                    ...(isRegenerate ? { regenerate: true } : {}),
                },
                { signal: controller.signal, idempotencyKey: this.deps.createId() },
            )

            for await (const event of stream) {
                // 停止或切换会话后，迟到的事件既不能追加内容，也不能触发交接
                if (!this.isCurrentRun(runId) || this.isStopRequested) {
                    break
                }
                await this.dispatch(event, runId)
                if (this.turn === null || this.turn.isClosed) {
                    break
                }
            }

            this.settleAfterStream(runId)
        } catch (error) {
            if (this.isCurrentRun(runId)) {
                this.handleStreamFailure(error)
            }
        } finally {
            if (this.isCurrentRun(runId)) {
                this.controller = null
                this.isStopRequested = false
            }
        }
    }

    /** 会话切换或运行被顶替：中止在途流并丢弃所有临时状态 */
    private cancelRun(): void {
        this.activeRunId = 0
        this.controller?.abort()
        this.controller = null
        this.turn = null
        this.isStopRequested = false
        // 目标会话即将重建快照，缓冲内容不能写回旧会话
        this.discardPending()
    }

    private beginRun(
        threadId: string,
        content: string,
        isRetry: boolean,
        isRegenerate: boolean,
    ): number {
        this.nextRunId += 1
        this.activeRunId = this.nextRunId
        // 上一轮的残余缓冲不能混入新一轮
        this.discardPending()

        const turnId = this.deps.createId()
        const assistantId = createAssistantId(turnId)
        const messages = buildTurnMessages({
            messages: this.snapshot.messages,
            content,
            isRetry,
            userId: createUserId(turnId),
            assistantId,
            now: this.deps.now(),
        })

        this.turn = { threadId, assistantId, isClosed: false }
        this.publish({
            sessionId: threadId,
            messages,
            status: 'streaming',
            isStreaming: true,
            error: null,
            canRetry: false,
            isRegenerating: isRegenerate,
        })

        return this.activeRunId
    }

    private isCurrentRun(runId: number): boolean {
        return this.activeRunId === runId
    }

    private settleAfterStream(runId: number): void {
        if (!this.isCurrentRun(runId)) {
            return
        }

        if (this.isStopRequested) {
            this.cancelTurn()
            return
        }

        // 服务端成功路径一定会发 done；没有 done 说明流被截断，需如实标记为可重试
        if (this.turn !== null && !this.turn.isClosed) {
            this.failTurn(INCOMPLETE_CODE, MESSAGE_KEYS.interrupted)
        }
    }

    private async dispatch(event: ChatStreamEvent, runId: number): Promise<void> {
        switch (event.type) {
            case 'token':
                this.queueToken(event.text)
                return
            case 'reasoning':
                this.queueReasoning(event.text)
                return
            case 'tool_call':
                // 工具事件必须晚于之前的正文，先同步写回缓冲
                this.flushPending()
                this.pushToolCall(event.name, event.args)
                return
            case 'tool_result':
                this.flushPending()
                this.updateAssistant((message) =>
                    attachToolResult(message, event.name ?? '', event.preview, this.deps.now()),
                )
                return
            case 'done':
                this.flushPending()
                await this.completeTurn(event.threadId, runId)
                return
            case 'error':
                this.flushPending()
                this.failTurn(event.code, MESSAGE_KEYS.stream, event.message)
                return
            default:
                // 未知事件（例如服务端新增类型）忽略即可，不能中断已经开始的流
                return
        }
    }

    /** token 只入缓冲，由帧调度统一写回；终态与工具事件会强制 flush */
    private queueToken(text: string): void {
        if (!text) {
            return
        }
        this.pendingContent += text
        this.scheduleFlush()
    }

    private queueReasoning(text: string): void {
        if (!text) {
            return
        }
        this.pendingReasoning += text
        this.scheduleFlush()
    }

    private scheduleFlush(): void {
        if (this.cancelScheduledFlush) {
            return
        }

        const schedule = this.deps.scheduleFrame ?? scheduleAnimationFrame
        this.cancelScheduledFlush = schedule(() => {
            this.cancelScheduledFlush = null
            this.flushPending()
        })
    }

    /**
     * 把缓冲文本一次性写回快照。
     *
     * 取消已排期的帧回调，保证同一次 flush 不会重复执行；缓冲为空时直接返回，
     * 避免无内容变化也触发订阅者重渲染。
     */
    private flushPending(): void {
        this.cancelScheduledFlush?.()
        this.cancelScheduledFlush = null

        const content = this.pendingContent
        const reasoning = this.pendingReasoning
        if (!content && !reasoning) {
            return
        }

        this.pendingContent = ''
        this.pendingReasoning = ''
        this.updateAssistant((message) => {
            let next = message
            if (reasoning) {
                next = appendReasoning(next, reasoning)
            }
            return content ? appendToken(next, content) : next
        })
    }

    /** 丢弃缓冲：会话切换、重置轮次时使用，不能让旧内容污染新快照 */
    private discardPending(): void {
        this.cancelScheduledFlush?.()
        this.cancelScheduledFlush = null
        this.pendingContent = ''
        this.pendingReasoning = ''
    }

    private updateAssistant(updater: (message: RuntimeMessage) => RuntimeMessage): void {
        const turn = this.turn
        if (!turn || turn.isClosed) {
            return
        }

        const messages = updateMessage(this.snapshot.messages, turn.assistantId, updater)
        if (messages === this.snapshot.messages) {
            return
        }

        this.publish({ ...this.snapshot, messages })
    }

    private pushToolCall(name: string, args: Record<string, unknown>): void {
        const turn = this.turn
        if (!turn || turn.isClosed) {
            return
        }

        this.updateAssistant((message) => {
            const stepId = createStepId(turn.assistantId, message.steps.length)
            const step = createToolStep(stepId, name, args, this.deps.now())
            return appendToolStep(message, step)
        })
    }

    private async completeTurn(threadId: string, runId: number): Promise<void> {
        const turn = this.turn
        if (!turn || turn.isClosed) {
            return
        }

        // 终态前兜底：任何尚未写回的 token 都要先进入消息内容
        this.flushPending()
        const resolvedThreadId = threadId.trim() || turn.threadId
        // 先更新消息状态再关闭 turn，否则 updateAssistant 会直接返回
        this.updateAssistant((message) => ({ ...message, status: 'done' }))
        turn.isClosed = true
        this.publish({
            ...this.snapshot,
            sessionId: resolvedThreadId,
            status: 'done',
            isStreaming: false,
        })

        await handoffTurn({
            threadId: resolvedThreadId,
            runId,
            deps: this.deps,
            isCurrentRun: (id) => this.isCurrentRun(id),
            onSuccess: () => {
                this.turn = null
                this.controller = null
                this.publish(createEmptySnapshot(resolvedThreadId))
            },
            onFailure: (error) => {
                this.failTurn(toErrorCode(error), MESSAGE_KEYS.sync, describeError(error))
            },
        })
    }

    private cancelTurn(): void {
        // 先写回已生成的 token，再关闭 turn，否则 updateAssistant 会丢弃缓冲
        this.flushPending()
        const now = this.deps.now()
        this.updateAssistant((message) => ({
            ...finalizeSteps(message, 'stopped', now),
            status: 'cancelled',
        }))
        if (this.turn) {
            this.turn.isClosed = true
        }
        this.publish({
            ...this.snapshot,
            status: 'cancelled',
            isStreaming: false,
            canRetry: true,
            error: null,
        })
    }

    private handleStreamFailure(error: unknown): void {
        if (this.isStopRequested || isAbortError(error)) {
            this.cancelTurn()
            return
        }

        const normalized = normalizeError(error)
        const hasContent = findLastByRole(this.snapshot.messages, 'assistant')?.content !== ''
        // 已经输出过内容时属于流中断；建立流之前失败则是请求失败
        this.failTurn(
            String(normalized.code),
            hasContent ? MESSAGE_KEYS.interrupted : MESSAGE_KEYS.request,
            normalized.message,
        )
    }

    private failTurn(code: string, messageKey: string, detail: string | null = null): void {
        // 失败也要保留已经流出的内容，缓冲必须先写回
        this.flushPending()
        const now = this.deps.now()
        this.updateAssistant((message) => ({
            ...finalizeSteps(message, 'error', now),
            status: 'error',
        }))
        if (this.turn) {
            this.turn.isClosed = true
        }
        this.publish({
            ...this.snapshot,
            status: 'error',
            isStreaming: false,
            canRetry: true,
            error: { code, messageKey, detail, isRetryable: true },
        })
    }

    private publish(snapshot: AgentRuntimeSnapshot): void {
        this.snapshot = snapshot
        for (const listener of this.listeners) {
            listener()
        }
    }
}
