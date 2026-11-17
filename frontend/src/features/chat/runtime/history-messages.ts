import type { SessionMessage } from '@/features/sessions/api'
import { toCitations } from '@/features/sessions/api'

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
        // 优先用服务端稳定消息 ID：刷新与分页前后同一个消息始终命中同一条记录，
        // 反馈也据此绑定；旧服务端未下发 message_id 时退回「会话 + 下标」
        const id = item.message_id ? `message:${item.message_id}` : `history:${threadId}:${index}`
        const messageId = item.message_id
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
            // 历史里带待恢复中断：刷新后仍显示表单，并按等待输入而非已完成渲染
            const status = item.hitl ? 'awaiting_input' : 'done'
            const message = createRuntimeMessage({
                id,
                role: 'assistant',
                content: item.content,
                status,
                now: timestamp,
            })
            const steps = (item.tool_calls ?? []).map((call, stepIndex) =>
                createHistoryStep(threadId, index, stepIndex, call),
            )
            // 服务端已持久化结果时直接使用；旧数据回退到本轮内存/会话缓存
            const buildResult = item.buildResult ?? readBuildResult(threadId, item.content)
            // 引用随消息元数据回放；思考正文不落库，只保留「本回合可见」标记
            const citations = toCitations(item.citations)
            messages.push({
                ...message,
                steps,
                ...(messageId ? { messageId } : {}),
                ...(buildResult ? { buildResult } : {}),
                ...(item.hitl ? { hitl: item.hitl } : {}),
                ...(citations.length > 0 ? { citations } : {}),
                ...(item.had_reasoning === true ? { hadReasoning: true } : {}),
            })
            return
        }

        if (item.role === 'tool') {
            attachHistoryResult(messages, item)
        }
    })

    return messages
}
