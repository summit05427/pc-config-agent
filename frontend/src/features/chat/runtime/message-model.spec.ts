import { describe, expect, it } from 'vitest'

import {
    ACTIVITY_PREVIEW_LENGTH,
    appendReasoning,
    appendToken,
    appendToolStep,
    attachToolResult,
    createRuntimeMessage,
    createToolStep,
    finalizeSteps,
    findLastByRole,
    mergeMessages,
    mergeSteps,
    serializeArgs,
    updateMessage,
} from './message-model'
import type { RuntimeMessage, RuntimeToolStep } from './types'

const createMessage = (overrides: Partial<RuntimeMessage> = {}): RuntimeMessage => ({
    id: 'assistant-1',
    role: 'assistant',
    content: '',
    reasoning: '',
    steps: [],
    status: 'streaming',
    createdAt: 1000,
    ...overrides,
})

const createStep = (overrides: Partial<RuntimeToolStep> = {}): RuntimeToolStep => ({
    id: 'step-1',
    name: 'search',
    args: '{}',
    result: '',
    status: 'running',
    startedAt: 1000,
    finishedAt: null,
    ...overrides,
})

describe('mergeMessages', () => {
    it('按稳定 ID 去重，重复消息不会产生第二个气泡', () => {
        const existing = [
            createRuntimeMessage({
                id: 'user:1',
                role: 'user',
                content: '问题',
                status: 'done',
                now: 1,
            }),
        ]
        const incoming = [
            createRuntimeMessage({
                id: 'user:1',
                role: 'user',
                content: '重复的问题',
                status: 'done',
                now: 2,
            }),
            createRuntimeMessage({
                id: 'assistant:1',
                role: 'assistant',
                content: '',
                status: 'pending',
                now: 2,
            }),
        ]

        const merged = mergeMessages(existing, incoming)

        expect(merged).toHaveLength(2)
        expect(merged[0]?.content).toBe('问题')
        expect(merged[1]?.id).toBe('assistant:1')
    })

    it('工具步骤同样按 ID 去重', () => {
        const step = createStep()

        expect(mergeSteps([step], [step, createStep({ id: 'step-2' })])).toHaveLength(2)
    })
})

describe('updateMessage', () => {
    it('目标不存在时返回原数组，供调用方按引用相等跳过渲染', () => {
        const messages = [createMessage()]

        expect(updateMessage(messages, 'missing', (message) => message)).toBe(messages)
    })

    it('命中时只替换目标消息', () => {
        const messages = [createMessage(), createMessage({ id: 'assistant-2' })]

        const next = updateMessage(messages, 'assistant-2', (message) => ({
            ...message,
            status: 'done',
        }))

        expect(next).toHaveLength(2)
        expect(next[1]?.status).toBe('done')
        expect(messages[1]?.status).toBe('streaming')
    })
})

describe('流式消息更新', () => {
    it('首个 token 把 pending 提升为 streaming，后续 token 保持状态', () => {
        const pending = createMessage({ status: 'pending' })
        const started = appendToken(pending, '你')
        const continued = appendToken(started, '好')

        expect(started.status).toBe('streaming')
        expect(continued.status).toBe('streaming')
        expect(continued.content).toBe('你好')
    })

    it('追加工具步骤并按 ID 去重', () => {
        const step = createStep()

        expect(appendToolStep(createMessage(), step).steps).toHaveLength(1)
        expect(appendToolStep(createMessage({ steps: [step] }), step).steps).toHaveLength(1)
    })

    it('思考内容独立累积，不混入正文', () => {
        const pending = createMessage({ status: 'pending' })
        const started = appendReasoning(pending, '先分析')
        const continued = appendReasoning(started, '再回答')

        expect(started.status).toBe('streaming')
        expect(continued.reasoning).toBe('先分析再回答')
        expect(continued.content).toBe('')
        expect(appendToken(continued, '答案').content).toBe('答案')
    })

    it('工具结果优先挂回最近一个同名步骤，否则回填最后一个运行中步骤', () => {
        const steps = [
            createStep({ id: 'step-1', name: 'search' }),
            createStep({ id: 'step-2', name: 'search' }),
            createStep({ id: 'step-3', name: 'fetch' }),
        ]
        const message = createMessage({ steps })

        const sameName = attachToolResult(message, 'search', '结果', 2000)
        expect(sameName.steps[1]).toMatchObject({ status: 'done', result: '结果', finishedAt: 2000 })
        expect(sameName.steps[0]?.status).toBe('running')

        const fallback = attachToolResult(message, 'unknown', '兜底', 3000)
        expect(fallback.steps[2]).toMatchObject({ status: 'done', result: '兜底' })
    })

    it('没有运行中的步骤时不产生新对象', () => {
        const message = createMessage({
            steps: [createStep({ status: 'done', finishedAt: 1 })],
        })

        expect(attachToolResult(message, 'search', '结果', 2)).toBe(message)
    })

    it('中断或失败时只把运行中的步骤标记为终态', () => {
        const message = createMessage({
            steps: [createStep(), createStep({ id: 'step-2', status: 'done', finishedAt: 1 })],
        })

        const stopped = finalizeSteps(message, 'stopped', 2000)
        expect(stopped.steps[0]).toMatchObject({ status: 'stopped', finishedAt: 2000 })
        expect(stopped.steps[1]?.status).toBe('done')
    })
})

describe('工具参数与查找', () => {
    it('参数序列化后截断到统一预览长度', () => {
        const serialized = serializeArgs({ value: 'x'.repeat(ACTIVITY_PREVIEW_LENGTH + 100) })

        expect(serialized).toHaveLength(ACTIVITY_PREVIEW_LENGTH)
    })

    it('循环引用不会中断整个流', () => {
        const circular: Record<string, unknown> = {}
        circular.self = circular

        expect(serializeArgs(circular)).toBe('')
    })

    it('findLastByRole 返回最后一条指定角色，空列表返回 undefined', () => {
        const messages = [
            createMessage({ id: 'user:1', role: 'user', content: '旧' }),
            createMessage({ id: 'user:2', role: 'user', content: '新' }),
        ]

        expect(findLastByRole(messages, 'user')?.content).toBe('新')
        expect(findLastByRole([], 'user')).toBeUndefined()
    })

    it('创建工具步骤时带上 running 初值与序列化参数', () => {
        const step = createToolStep('step-1', 'search', { q: 'x' }, 1000)

        expect(step).toMatchObject({ status: 'running', args: '{"q":"x"}', finishedAt: null })
    })
})
