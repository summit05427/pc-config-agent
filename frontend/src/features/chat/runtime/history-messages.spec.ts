import { describe, expect, it } from 'vitest'

import type { SessionMessage } from '@/features/sessions/api'

import { mapHistoryMessages } from './history-messages'

const THREAD_ID = 'thread-hitl'

const HITL = {
    interruptId: 'int-1',
    interactionType: 'clarify_requirements',
    question: '请补充预算',
    fields: [{ name: 'budget_yuan', label: '预算', type: 'number' as const, required: true }],
    submitLabel: '继续',
    context: {},
}

describe('mapHistoryMessages HITL', () => {
    it('历史里带 hitl 的助手消息映射为 awaiting_input 并保留表单', () => {
        const history: SessionMessage[] = [
            { role: 'user', content: '帮我配台电脑' },
            { role: 'assistant', content: '请补充预算', hitl: HITL },
        ]

        const messages = mapHistoryMessages(THREAD_ID, history)

        expect(messages[1]?.status).toBe('awaiting_input')
        expect(messages[1]?.hitl).toEqual(HITL)
    })

    it('没有 hitl 的历史保持 done，不渲染表单', () => {
        const history: SessionMessage[] = [
            { role: 'user', content: '帮我配台电脑' },
            { role: 'assistant', content: '配置如下' },
        ]

        const messages = mapHistoryMessages(THREAD_ID, history)

        expect(messages[1]?.status).toBe('done')
        expect(messages[1]?.hitl).toBeUndefined()
    })
})

describe('mapHistoryMessages 稳定消息 ID', () => {
    it('优先使用服务端 message_id 生成 key 与反馈标识', () => {
        const history: SessionMessage[] = [
            { message_id: 't-1:0', role: 'user', content: '你好' },
            { message_id: 't-1:1', role: 'assistant', content: '你好，有什么可以帮你？' },
        ]

        const messages = mapHistoryMessages('t-1', history)

        expect(messages[0]?.id).toBe('message:t-1:0')
        expect(messages[1]?.id).toBe('message:t-1:1')
        expect(messages[1]?.messageId).toBe('t-1:1')
    })

    it('旧服务端缺少 message_id 时退回会话下标，且不伪造反馈标识', () => {
        const history: SessionMessage[] = [
            { role: 'user', content: '你好' },
            { role: 'assistant', content: '收到' },
        ]

        const messages = mapHistoryMessages('t-2', history)

        expect(messages[1]?.id).toBe('history:t-2:1')
        expect(messages[1]?.messageId).toBeUndefined()
    })
})
