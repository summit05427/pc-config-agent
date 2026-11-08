import { useCallback, useSyncExternalStore } from 'react'

import { getSharedAgentRuntime } from '@/features/chat/runtime/deps'
import type { AgentRuntime } from '@/features/chat/runtime/agent-runtime'
import type { AgentRuntimeSnapshot } from '@/features/chat/runtime/types'

export interface UseAgentRuntimeResult {
    readonly runtime: AgentRuntime
    readonly snapshot: AgentRuntimeSnapshot
    readonly send: (text: string, model?: string | null) => Promise<void>
    readonly stop: () => void
    readonly retry: (model?: string | null) => Promise<void>
    readonly regenerate: (content: string, model?: string | null) => Promise<void>
}

/**
 * 订阅 Agent 运行时的流式状态。
 *
 * 运行时是 React 之外的独立状态源，组件只做订阅，不把流式 token 写进 Zustand
 * 或 Query Cache。请求只由事件处理函数触发，不在 effect 中自动发起，
 * 因此 StrictMode 的双调用不会产生重复请求。
 */
export function useAgentRuntime(runtime?: AgentRuntime): UseAgentRuntimeResult {
    const activeRuntime = runtime ?? getSharedAgentRuntime()

    // 第三个参数同时用作服务端快照：运行时没有 SSR 需求，直接返回当前值即可
    const snapshot = useSyncExternalStore(
        activeRuntime.subscribe,
        activeRuntime.getSnapshot,
        activeRuntime.getSnapshot,
    )

    const send = useCallback(
        (text: string, model?: string | null) => activeRuntime.send(text, model),
        [activeRuntime],
    )

    const stop = useCallback(() => {
        activeRuntime.stop()
    }, [activeRuntime])

    const retry = useCallback(
        (model?: string | null) => activeRuntime.retry(model),
        [activeRuntime],
    )

    const regenerate = useCallback(
        (content: string, model?: string | null) => activeRuntime.regenerate(content, model),
        [activeRuntime],
    )

    return { runtime: activeRuntime, snapshot, send, stop, retry, regenerate }
}
