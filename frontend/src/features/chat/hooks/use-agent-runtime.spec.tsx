import { StrictMode, type ReactNode } from 'react'
import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AgentRuntime } from '@/features/chat/runtime/agent-runtime'
import { getSharedAgentRuntime } from '@/features/chat/runtime/deps'
import type { AgentRuntimeDeps } from '@/features/chat/runtime/types'

import { useAgentRuntime } from './use-agent-runtime'

const StrictModeWrapper = ({ children }: { children: ReactNode }) => (
    <StrictMode>{children}</StrictMode>
)

const createRuntime = (stream: AgentRuntimeDeps['stream']): AgentRuntime =>
    new AgentRuntime({
        stream,
        createId: () => 'runtime-id',
        now: () => 1000,
        getPreferences: async () => null,
        confirmPersisted: async () => undefined,
        invalidateHistory: async () => undefined,
        invalidateSessions: async () => undefined,
        syncHistory: async () => undefined,
    })

const userMessages = (runtime: AgentRuntime): number =>
    runtime.getSnapshot().messages.filter((message) => message.role === 'user').length

describe('useAgentRuntime', () => {
    it('StrictMode 挂载不自动发请求，重复提交只请求一次', async () => {
        let requestCount = 0
        const runtime = createRuntime(async function* () {
            requestCount += 1
            yield { type: 'token', text: '答复' }
            yield { type: 'done', threadId: 'thread-1' }
        })

        const { result } = renderHook(() => useAgentRuntime(runtime), {
            wrapper: StrictModeWrapper,
        })

        expect(requestCount).toBe(0)
        expect(result.current.snapshot.status).toBe('idle')

        await act(async () => {
            await Promise.all([result.current.send('问题'), result.current.send('问题')])
        })

        expect(requestCount).toBe(1)
        // 交接完成后临时消息清空，历史交给 Query
        expect(result.current.snapshot).toMatchObject({ status: 'idle', messages: [] })
    })

    it('失败后通过 retry 复用原提问，只发起一次新的流', async () => {
        let requestCount = 0
        const runtime = createRuntime(async function* () {
            requestCount += 1
            if (requestCount === 1) {
                yield { type: 'error', code: 'upstream', message: '模型不可用' }
                return
            }
            yield { type: 'token', text: '第二次答复' }
            yield { type: 'done', threadId: 'thread-1' }
        })

        const { result } = renderHook(() => useAgentRuntime(runtime))

        await act(async () => {
            await result.current.send('问题')
        })

        expect(result.current.snapshot.status).toBe('error')
        expect(result.current.snapshot.canRetry).toBe(true)
        expect(userMessages(runtime)).toBe(1)
        expect(result.current.snapshot.messages[0]?.content).toBe('问题')

        await act(async () => {
            await result.current.retry()
        })

        expect(requestCount).toBe(2)
        expect(result.current.snapshot.status).toBe('idle')
    })

    it('停止生成会中断在途流并保留已生成内容', async () => {
        let isStreamAborted = false
        let notifyTokenPublished: () => void = () => undefined
        // 生成器在首个 token 被消费后才释放该信号，用来确认 token 已经进入快照
        const tokenPublished = new Promise<void>((resolve) => {
            notifyTokenPublished = resolve
        })

        const runtime = createRuntime(async function* (_payload, options) {
            const signal = options.signal
            // 模拟真实流：收到 abort 后立即抛出 AbortError，而不是继续产出事件
            const aborted = new Promise<never>((_, reject) => {
                signal?.addEventListener('abort', () => {
                    isStreamAborted = true
                    reject(new DOMException('Aborted', 'AbortError'))
                })
            })

            yield { type: 'token', text: '已生成的内容' }
            notifyTokenPublished()
            await aborted
        })

        const { result } = renderHook(() => useAgentRuntime(runtime))

        await act(async () => {
            const pending = result.current.send('问题')
            // 等首个 token 真正进入快照后再停止，覆盖「看到部分回答后点停止」的真实路径
            await tokenPublished
            result.current.stop()
            await pending
        })

        expect(isStreamAborted).toBe(true)
        expect(result.current.snapshot.status).toBe('cancelled')
        expect(result.current.snapshot.canRetry).toBe(true)
        expect(result.current.snapshot.messages.at(-1)).toMatchObject({
            content: '已生成的内容',
            status: 'cancelled',
        })
    })

    it('空闲状态下 stop 不改变快照', () => {
        const runtime = createRuntime(async function* () {})
        const { result } = renderHook(() => useAgentRuntime(runtime))

        act(() => {
            result.current.stop()
        })

        expect(result.current.snapshot.status).toBe('idle')
    })

    it('未注入实例时使用应用级共享运行时', () => {
        const { result } = renderHook(() => useAgentRuntime())

        expect(result.current.runtime).toBe(getSharedAgentRuntime())
    })
})
