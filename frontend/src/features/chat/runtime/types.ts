import type {
    BuildResult,
    ChatCitation,
    ChatPreferences,
    ChatRequest,
    ChatStage,
    ChatStreamEvent,
    HitlInterrupt,
    StreamChatOptions,
} from '@/features/sessions/api'

/** 与 Vue 基线的 agent-chat-message 保持一致的消息状态，渲染层据此展示不同终态 */
export type ChatMessageStatus =
    | 'pending'
    | 'streaming'
    | 'done'
    | 'cancelled'
    | 'error'
    /** HITL：本轮已暂停，等待用户填写表单 */
    | 'awaiting_input'

/** 工具步骤的终态：完成、被用户停止、失败；running 表示仍在等待结果 */
export type ToolStepStatus = 'running' | 'done' | 'stopped' | 'error'

export interface RuntimeToolStep {
    readonly id: string
    readonly name: string
    readonly args: string
    readonly result: string
    readonly status: ToolStepStatus
    readonly startedAt: number
    readonly finishedAt: number | null
}

export interface RuntimeMessage {
    readonly id: string
    /** 服务端稳定消息标识；仅助手消息可能持有，用于绑定反馈，缺失时隐藏反馈入口 */
    readonly messageId?: string
    readonly role: 'user' | 'assistant'
    readonly content: string
    /** 思考内容：与正文分离，只存在于本次流式会话，不落库也不进入历史 */
    readonly reasoning: string
    /** 服务端按节点完成推进的阶段；工具事件成批到达时用它避免长时间停在「解析需求」 */
    readonly stage?: ChatStage
    readonly steps: readonly RuntimeToolStep[]
    readonly status: ChatMessageStatus
    readonly createdAt: number
    /** `done.build_result` 的结构化副本；仅当前轮临时消息持有，历史回放走 Markdown */
    readonly buildResult?: BuildResult
    /** HITL 中断提示；仅等待用户回答的消息持有，提交后随新一轮替换 */
    readonly hitl?: HitlInterrupt
    /**
     * RAG 检索引用。
     *
     * 流式期间由 `citations` 事件下发；历史接口从消息元数据回放，
     * 因此刷新页面后引用仍然可查看。
     */
    readonly citations?: readonly ChatCitation[]
    /**
     * 历史回放的思考可见性标记：思考正文只在当轮流式期间存在，
     * 刷新后仅提示「本回合可见」，不伪造内容。
     */
    readonly hadReasoning?: boolean
}

export type AgentRuntimeStatus =
    | 'idle'
    | 'streaming'
    | 'done'
    | 'cancelled'
    | 'error'
    /** 本轮已暂停，等待用户回答，不属于失败 */
    | 'awaiting_input'

/**
 * 失败状态只保留 i18n key 与服务端原始细节。
 *
 * 运行时不属于 React，无法调用 `t()`；把文案 key 留给渲染层翻译，
 * 既保证多语言一致，也避免在运行时里写死任何一种语言的字符串。
 */
export interface AgentRuntimeError {
    readonly code: string
    readonly messageKey: string
    readonly detail: string | null
    readonly isRetryable: boolean
}

export interface AgentRuntimeSnapshot {
    readonly sessionId: string | null
    /** 仅包含当前会话尚未写入 Query 的临时消息；交接完成后清空 */
    readonly messages: readonly RuntimeMessage[]
    readonly status: AgentRuntimeStatus
    readonly isStreaming: boolean
    readonly error: AgentRuntimeError | null
    readonly canRetry: boolean
    /** 本轮是否为「重新生成」：期间隐藏历史最后一组提问与回答 */
    readonly isRegenerating: boolean
}

/**
 * 运行时依赖全部注入，便于单测用确定性流替换真实网络与 Query。
 *
 * `confirmPersisted → invalidateHistory → syncHistory → invalidateSessions`
 * 对应 D-09 的交接顺序（列表刷新放在临时消息清理之后，避免同帧抖动），
 * 生产实现见 `deps.ts`，测试可用 spy 断言调用先后。
 */
export interface AgentRuntimeDeps {
    readonly stream: (
        payload: ChatRequest,
        options: StreamChatOptions,
    ) => AsyncGenerator<ChatStreamEvent>
    /**
     * 读取本轮要下发的用户偏好。
     *
     * Agent 只从请求体读偏好、不查库，因此每轮都要取一次；
     * 返回 `null` 表示读取失败，按「偏好失败不阻断对话」降级为不携带。
     */
    readonly getPreferences: () => Promise<ChatPreferences | null>
    readonly confirmPersisted: (threadId: string) => Promise<void>
    readonly invalidateHistory: (threadId: string) => Promise<void>
    /** 失效会话列表；首问完成后让新会话立即出现在侧栏 */
    readonly invalidateSessions: () => Promise<void>
    readonly syncHistory: (threadId: string) => Promise<void>
    readonly createId: () => string
    readonly now: () => number
    /**
     * 帧调度：把一次缓冲刷新推迟到下一帧，返回取消函数。
     *
     * 默认实现使用 `requestAnimationFrame`；测试注入手动调度即可获得
     * 确定性的 flush 时机，不必依赖真实帧率。
     */
    readonly scheduleFrame?: (callback: () => void) => () => void
}
