import type { SessionMessage } from '@/features/sessions/api'

import { readBuildResult } from './build-result-cache'
import { attachToolResult, createRuntimeMessage, serializeArgs } from './message-model'
import type { RuntimeMessage, RuntimeToolStep } from './types'

/** 历史消息没有客户端观测时间，置 0 后界面不会展示伪造的耗时 */
const NO_TIMESTAMP = 0

const createHistoryStep = (
    threadId: string,
    messageIndex: number,
    stepIndex: number,
    call: NonNullable<SessionMessage['tool_calls']>[number],
): RuntimeToolStep => ({
    id: `history:${threadId}:${messageIndex}:step:${stepIndex}`,
    name: call.name,
    args: serializeArgs(call.args),
    result: '',
    status: 'done',
    startedAt: NO_TIMESTAMP,
    finishedAt: null,
})

/** tool 消息不单独成气泡，统一回填到上一条 assistant 的步骤上 */
const attachHistoryResult = (messages: RuntimeMessage[], item: SessionMessage): void => {
    const lastIndex = messages.length - 1
    const last = messages[lastIndex]
    if (!last || last.role !== 'assistant') {
        return
    }

    messages[lastIndex] = attachToolResult(last, item.name ?? '', item.content, NO_TIMESTAMP)
}

/**
 * 把服务端历史映射为页面消息模型。
 *
 * ID 由「会话 + 下标」组成，保证刷新、重新同步与流式交接时同一份历史始终命中
 * 同一个 React key；历史里的工具调用与实时流一样展示为执行轨迹，而不是独立气泡。
 */
export function mapHistoryMessages(
    threadId: string,
    history: readonly SessionMessage[],
): RuntimeMessage[] {
    const messages: RuntimeMessage[] = []

    history.forEach((item, index) => {
        const id = `history:${threadId}:${index}`
        // 服务端写入时间优先；旧数据没有 created_at 时保持 0，界面不展示伪造时间
        const createdAt = item.created_at ? Date.parse(item.created_at) : NO_TIMESTAMP
        const timestamp = Number.isNaN(createdAt) ? NO_TIMESTAMP : createdAt

        if (item.role === 'user') {
            messages.push(
                createRuntimeMessage({
                    id,
                    role: 'user',
                    content: item.content,
                    status: 'done',
                    now: timestamp,
                }),
            )
            return
        }

        if (item.role === 'assistant') {
            const message = createRuntimeMessage({
                id,
                role: 'assistant',
                content: item.content,
                status: 'done',
                now: timestamp,
            })
            const steps = (item.tool_calls ?? []).map((call, stepIndex) =>
                createHistoryStep(threadId, index, stepIndex, call),
            )
            // 同一轮刚完成时用内存缓存恢复卡片；刷新后无缓存则保持 Markdown
            const buildResult = readBuildResult(threadId, item.content)
            messages.push({ ...message, steps, ...(buildResult ? { buildResult } : {}) })
            return
        }

        if (item.role === 'tool') {
            attachHistoryResult(messages, item)
        }
    })

    return messages
}
