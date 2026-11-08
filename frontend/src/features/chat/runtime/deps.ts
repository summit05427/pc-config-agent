import type { QueryClient } from '@tanstack/react-query'

import { queryClient as appQueryClient } from '@/app/query-client'
import { getPreferences as fetchUserPreferences, type UserPreferences } from '@/features/settings/api'
import {
    getSessionMessages,
    sessionMessagesQueryOptions,
    streamChat,
    type ChatPreferences,
} from '@/features/sessions/api'
import { queryKeys } from '@/shared/lib/query-keys'

import { AgentRuntime } from './agent-runtime'
import { clearDraftThread, createThreadId } from './agent-thread'
import type { AgentRuntimeDeps } from './types'

/** 确认落库只取最新 1 条，避免为了一次确认再拉整页历史 */
const CONFIRM_PAGE_SIZE = 1

/**
 * Java 偏好接口是 camelCase，Agent 请求体是 snake_case。
 *
 * 转换只允许出现在这里：业务组件继续用 camelCase，Agent 契约保持 snake_case。
 */
export const toChatPreferences = (preferences: UserPreferences): ChatPreferences => ({
    instructions: preferences.instructions,
    reply_language: preferences.replyLanguage,
    response_style: preferences.responseStyle,
    use_history: preferences.useHistory,
})

export interface CreateAgentRuntimeDepsOptions {
    readonly queryClient?: QueryClient
}

/**
 * 生产依赖。
 *
 * - `confirmPersisted`：done 之后先验证服务端确实能读到该会话，避免提前 invalidate；
 * - `invalidateHistory`：只失效当前会话的历史 key，分页组合由前缀 key 统一命中；
 * - `invalidateSessions`：失效所有会话列表，首问完成后侧栏立即出现新会话；
 * - `syncHistory`：通过同一份 Query 缓存重新拉取，历史仍是服务端数据的唯一来源。
 */
export const createAgentRuntimeDeps = (
    options: CreateAgentRuntimeDepsOptions = {},
): AgentRuntimeDeps => {
    const client = options.queryClient ?? appQueryClient

    return {
        stream: streamChat,
        createId: createThreadId,
        now: () => Date.now(),
        // 偏好读取失败时降级为不携带，与 Vue 基线「偏好失败不阻断对话」语义一致
        getPreferences: async () => {
            try {
                return toChatPreferences(await fetchUserPreferences())
            } catch {
                return null
            }
        },
        confirmPersisted: async (threadId) => {
            await getSessionMessages(threadId, 1, CONFIRM_PAGE_SIZE, 'desc')
            // 服务端已能读到该会话，草稿阶段结束，历史查询随即恢复
            clearDraftThread(threadId)
        },
        invalidateHistory: async (threadId) => {
            await client.invalidateQueries({ queryKey: queryKeys.sessions.messagesAll(threadId) })
        },
        invalidateSessions: async () => {
            await client.invalidateQueries({ queryKey: queryKeys.sessions.lists })
        },
        syncHistory: async (threadId) => {
            await client.fetchQuery(sessionMessagesQueryOptions(threadId))
        },
    }
}

let sharedRuntime: AgentRuntime | null = null

/**
 * 应用内共享的运行时实例。
 *
 * 模块级单例保证路由切换、组件重新挂载时仍在跟随同一个在途流；
 * 运行时自身不依赖 React，组件只通过订阅读取快照。
 */
export const getSharedAgentRuntime = (): AgentRuntime => {
    sharedRuntime ??= new AgentRuntime(createAgentRuntimeDeps())
    return sharedRuntime
}
