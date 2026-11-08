import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/features/sessions/api/request', () => ({
    sendAgentRequest: vi.fn(),
    requestAgentJson: vi.fn(),
    requestAgentVoid: vi.fn(),
    buildAgentUrl: vi.fn(),
    INVALID_RESPONSE_MESSAGE: '响应解析失败',
}))

vi.mock('@/features/settings/api', () => ({
    getPreferences: vi.fn(),
}))

import { QueryClient } from '@tanstack/react-query'

import { streamChat } from '@/features/sessions/api'
import { requestAgentJson } from '@/features/sessions/api/request'
import { getPreferences as fetchUserPreferences } from '@/features/settings/api'
import { queryKeys } from '@/shared/lib/query-keys'

import { createAgentRuntimeDeps, getSharedAgentRuntime, toChatPreferences } from './deps'

const EMPTY_PAGE = { list: [], total: 0, page: 1, size: 100, thread_id: 'thread-1' }

const createClient = (): QueryClient =>
    new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })

beforeEach(() => {
    vi.mocked(requestAgentJson).mockReset()
    vi.mocked(requestAgentJson).mockResolvedValue(EMPTY_PAGE)
    vi.mocked(fetchUserPreferences).mockReset()
})

describe('createAgentRuntimeDeps', () => {
    it('确认落库只读取最新 1 条消息', async () => {
        const deps = createAgentRuntimeDeps({ queryClient: createClient() })

        await deps.confirmPersisted('thread-1')

        expect(requestAgentJson).toHaveBeenCalledWith(
            '/sessions/thread-1/messages',
            { method: 'GET' },
            { page: 1, size: 1, order: 'desc' },
        )
    })

    it('失效使用会话级前缀 key，命中所有分页与排序组合', async () => {
        const client = createClient()
        const invalidate = vi.spyOn(client, 'invalidateQueries')
        const deps = createAgentRuntimeDeps({ queryClient: client })

        await deps.invalidateHistory('thread-1')

        expect(invalidate).toHaveBeenCalledWith({
            queryKey: queryKeys.sessions.messagesAll('thread-1'),
        })
    })

    it('历史重新同步复用 Query 缓存并拉取默认分页', async () => {
        const client = createClient()
        const fetchQuery = vi.spyOn(client, 'fetchQuery')
        const deps = createAgentRuntimeDeps({ queryClient: client })

        await deps.syncHistory('thread-1')

        expect(fetchQuery).toHaveBeenCalledWith(
            expect.objectContaining({
                queryKey: queryKeys.sessions.messages('thread-1', 1, 100, 'desc'),
            }),
        )
        expect(requestAgentJson).toHaveBeenCalledWith(
            '/sessions/thread-1/messages',
            { method: 'GET' },
            { page: 1, size: 100, order: 'desc' },
        )
    })

    it('流式入口与 ID、时间依赖来自现有基础设施', () => {
        const deps = createAgentRuntimeDeps({ queryClient: createClient() })

        expect(deps.stream).toBe(streamChat)
        expect(deps.createId().length).toBeGreaterThan(0)
        expect(typeof deps.now()).toBe('number')
    })
})

describe('偏好下发依赖', () => {
    it('把 Java camelCase 偏好映射为 Agent snake_case', async () => {
        const deps = createAgentRuntimeDeps({ queryClient: createClient() })
        vi.mocked(fetchUserPreferences).mockResolvedValue({
            instructions: '用中文回答',
            replyLanguage: 'zh-CN',
            responseStyle: 'concise',
            useHistory: false,
            updatedAt: null,
        })

        await expect(deps.getPreferences()).resolves.toEqual({
            instructions: '用中文回答',
            reply_language: 'zh-CN',
            response_style: 'concise',
            use_history: false,
        })
    })

    it('偏好读取失败降级为 null，不阻断对话', async () => {
        const deps = createAgentRuntimeDeps({ queryClient: createClient() })
        vi.mocked(fetchUserPreferences).mockRejectedValue(new Error('network down'))

        await expect(deps.getPreferences()).resolves.toBeNull()
    })

    it('映射函数只做字段改名，不丢字段', () => {
        expect(
            toChatPreferences({
                instructions: null,
                replyLanguage: 'en-US',
                responseStyle: 'detailed',
                useHistory: true,
                updatedAt: '2026-10-31T00:00:00Z',
            }),
        ).toEqual({
            instructions: null,
            reply_language: 'en-US',
            response_style: 'detailed',
            use_history: true,
        })
    })
})

describe('getSharedAgentRuntime', () => {
    it('模块级单例保证路由切换后仍跟随同一个在途流', () => {
        expect(getSharedAgentRuntime()).toBe(getSharedAgentRuntime())
    })
})
