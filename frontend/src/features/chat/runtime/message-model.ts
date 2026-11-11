import type { ChatCitation } from '@/features/sessions/api'

import type { RuntimeMessage, RuntimeToolStep, ToolStepStatus } from './types'

/** 工具参数与结果的预览上限，和历史消息的展示长度保持一致 */
export const ACTIVITY_PREVIEW_LENGTH = 200

const truncate = (value: string): string => value.slice(0, ACTIVITY_PREVIEW_LENGTH)

const findLastIndex = <T>(items: readonly T[], predicate: (item: T) => boolean): number => {
    for (let index = items.length - 1; index >= 0; index -= 1) {
        const item = items[index]
        if (item !== undefined && predicate(item)) {
            return index
        }
    }
    return -1
}

/** 参数来自 JSON 解析结果，正常不会循环引用；兜底避免预览失败中断整个流 */
export const serializeArgs = (args: Record<string, unknown>): string => {
    try {
        return truncate(JSON.stringify(args) ?? '')
    } catch {
        return ''
    }
}

export interface CreateRuntimeMessageInit {
    readonly id: string
    readonly role: RuntimeMessage['role']
    readonly content: string
    readonly status: RuntimeMessage['status']
    readonly now: number
}

export const createRuntimeMessage = (init: CreateRuntimeMessageInit): RuntimeMessage => ({
    id: init.id,
    role: init.role,
    content: init.content,
    reasoning: '',
    steps: [],
    status: init.status,
    createdAt: init.now,
})

export const createToolStep = (
    id: string,
    name: string,
    args: Record<string, unknown>,
    now: number,
): RuntimeToolStep => ({
    id,
    name,
    args: serializeArgs(args),
    result: '',
    status: 'running',
    startedAt: now,
    finishedAt: null,
})

/**
 * 按稳定 ID 合并消息。
 *
 * 同一个 ID 只保留先到的一条，避免「流式气泡 + 历史回填」或重放事件
 * 在界面上出现两条相同消息。
 */
export const mergeMessages = (
    existing: readonly RuntimeMessage[],
    incoming: readonly RuntimeMessage[],
): RuntimeMessage[] => {
    const merged = [...existing]
    const seen = new Set(existing.map((message) => message.id))

    for (const message of incoming) {
        if (seen.has(message.id)) {
            continue
        }
        seen.add(message.id)
        merged.push(message)
    }

    return merged
}

/** 工具步骤同样按 ID 去重，保证重放 tool_call 不会多出一条执行记录 */
export const mergeSteps = (
    existing: readonly RuntimeToolStep[],
    incoming: readonly RuntimeToolStep[],
): RuntimeToolStep[] => {
    const merged = [...existing]
    const seen = new Set(existing.map((step) => step.id))

    for (const step of incoming) {
        if (seen.has(step.id)) {
            continue
        }
        seen.add(step.id)
        merged.push(step)
    }

    return merged
}

/** 找不到目标消息时返回原数组，调用方可用引用相等跳过无意义的重渲染 */
export const updateMessage = (
    messages: readonly RuntimeMessage[],
    id: string,
    updater: (message: RuntimeMessage) => RuntimeMessage,
): readonly RuntimeMessage[] => {
    const index = messages.findIndex((message) => message.id === id)
    if (index === -1) {
        return messages
    }

    const next = [...messages]
    next[index] = updater(messages[index] as RuntimeMessage)
    return next
}

export const appendToken = (message: RuntimeMessage, text: string): RuntimeMessage => ({
    ...message,
    content: message.content + text,
    status: message.status === 'pending' ? 'streaming' : message.status,
})

/**
 * 追加思考内容。
 *
 * 思考与正文分开累积：正文可复制、可交给生成式 UI，思考只用于过程展示，
 * 混在一起会污染复制内容与 Markdown 渲染。
 */
export const appendReasoning = (message: RuntimeMessage, text: string): RuntimeMessage => ({
    ...message,
    reasoning: message.reasoning + text,
    status: message.status === 'pending' ? 'streaming' : message.status,
})

export const appendToolStep = (message: RuntimeMessage, step: RuntimeToolStep): RuntimeMessage => ({
    ...message,
    steps: mergeSteps(message.steps, [step]),
})

/**
 * 把工具结果挂回最近一个同名且仍在运行的步骤。
 *
 * 服务端不保证 result 与 call 一一对应地携带关联 ID，因此按「同名优先、
 * 否则最近运行中」回填，避免出现孤立的结果记录。
 */
export const attachToolResult = (
    message: RuntimeMessage,
    name: string,
    preview: string,
    now: number,
): RuntimeMessage => {
    const running = message.steps.filter((step) => step.status === 'running')
    if (running.length === 0) {
        return message
    }

    const matchedIndex = findLastIndex(running, (step) => step.name === name)
    const target = matchedIndex === -1 ? (running[running.length - 1] as RuntimeToolStep) : running[matchedIndex]
    if (!target) {
        return message
    }

    return {
        ...message,
        steps: message.steps.map((step) =>
            step.id === target.id
                ? { ...step, result: truncate(preview), status: 'done', finishedAt: now }
                : step,
        ),
    }
}

/**
 * 挂载检索引用。
 *
 * 按 `sourceId` 去重：多轮检索可能重复推送同一来源，重复条目只会让折叠区
 * 变长而不增加信息量。没有新条目时返回原对象，避免流式期间无谓重渲染。
 */
export const attachCitations = (
    message: RuntimeMessage,
    citations: readonly ChatCitation[],
): RuntimeMessage => {
    const seen = new Set(message.citations?.map((citation) => citation.sourceId) ?? [])
    const incoming = citations.filter((citation) => !seen.has(citation.sourceId))
    if (incoming.length === 0) {
        return message
    }

    return { ...message, citations: [...(message.citations ?? []), ...incoming] }
}

/** 中断或失败时仍在运行的步骤如实标记为已停止，不伪装成完成 */
export const finalizeSteps = (
    message: RuntimeMessage,
    status: Extract<ToolStepStatus, 'stopped' | 'error'>,
    now: number,
): RuntimeMessage => ({
    ...message,
    steps: message.steps.map((step) =>
        step.status === 'running' ? { ...step, status, finishedAt: now } : step,
    ),
})

export const findLastByRole = (
    messages: readonly RuntimeMessage[],
    role: RuntimeMessage['role'],
): RuntimeMessage | undefined => {
    const index = findLastIndex(messages, (message) => message.role === role)
    return index === -1 ? undefined : messages[index]
}

export interface BuildTurnMessagesInit {
    readonly messages: readonly RuntimeMessage[]
    readonly content: string
    readonly isRetry: boolean
    readonly userId: string
    readonly assistantId: string
    readonly now: number
}

/**
 * 中断已作答：去掉表单并把该轮标记为完成。
 *
 * 表单由消息上的 `hitl` 驱动，提交后不清理会让同一 interrupt 一直可再次提交，
 * 服务端只会返回「中断不存在」，用户却以为还能改答案。
 */
export const clearAnsweredHitl = (messages: readonly RuntimeMessage[]): RuntimeMessage[] =>
    messages.map((message): RuntimeMessage =>
        message.hitl ? { ...message, status: 'done', hitl: undefined } : message,
    )

/**
 * 生成一轮对话的起始消息列表。
 *
 * 重试时复用原提问并替换最后一条失败回答，避免出现两条相同的用户气泡；
 * 其余情况按稳定 ID 合并，重复事件不会产生多余气泡。
 */
export const buildTurnMessages = (init: BuildTurnMessagesInit): RuntimeMessage[] => {
    const previousUser = init.isRetry ? findLastByRole(init.messages, 'user') : undefined
    const baseMessages =
        init.isRetry && init.messages.at(-1)?.role === 'assistant'
            ? init.messages.slice(0, -1)
            : init.messages

    const userMessage =
        previousUser ??
        createRuntimeMessage({
            id: init.userId,
            role: 'user',
            content: init.content,
            status: 'done',
            now: init.now,
        })

    const assistantMessage = createRuntimeMessage({
        id: init.assistantId,
        role: 'assistant',
        content: '',
        status: 'pending',
        now: init.now,
    })

    return mergeMessages(baseMessages, [userMessage, assistantMessage])
}
