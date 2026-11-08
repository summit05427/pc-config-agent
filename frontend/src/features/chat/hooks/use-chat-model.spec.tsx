import { StrictMode, type ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useChatModel } from './use-chat-model'

const { setSessionModelMock, toastErrorMock, catalogState } = vi.hoisted(() => ({
    setSessionModelMock: vi.fn(),
    toastErrorMock: vi.fn(),
    // 目录数据可在用例里替换，用于覆盖空目录与加载中分支
    catalogState: { list: [] as unknown[] },
}))

vi.mock('sonner', () => ({ toast: { error: toastErrorMock } }))

vi.mock('@/features/models/api', () => ({
    modelCatalogQueryOptions: {
        queryKey: ['models', 'catalog'],
        queryFn: () =>
            Promise.resolve({ list: catalogState.list, total: catalogState.list.length, page: 1, size: 100 }),
    },
}))

vi.mock('@/features/sessions/api', () => ({
    setSessionModel: (threadId: string, modelKey: string | null) =>
        setSessionModelMock(threadId, modelKey),
}))

const createClient = (): QueryClient =>
    new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })

const createWrapper = (client: QueryClient, useStrictMode = false) => {
    const Wrapper = ({ children }: { children: ReactNode }) => {
        const tree = <QueryClientProvider client={client}>{children}</QueryClientProvider>
        return useStrictMode ? <StrictMode>{tree}</StrictMode> : tree
    }
    return Wrapper
}

beforeEach(() => {
    catalogState.list = [
        {
            provider: 'openai',
            modelKey: 'openai:gpt-4o',
            displayName: 'GPT-4o',
            capabilities: ['text'],
            contextWindow: 128000,
        },
    ]
})

describe('useChatModel', () => {
    it('已落库会话直接采用会话模块传入的模型，切换后立即持久化', async () => {
        setSessionModelMock.mockResolvedValueOnce({ model_key: 'openai:gpt-4o-mini' })

        const { result } = renderHook(
            () =>
                useChatModel({
                    threadId: 'thread-1',
                    isPersisted: true,
                    sessionModelKey: 'openai:gpt-4o',
                }),
            { wrapper: createWrapper(createClient()) },
        )

        await waitFor(() => expect(result.current.isAvailable).toBe(true))
        expect(result.current.modelKey).toBe('openai:gpt-4o')

        act(() => {
            result.current.setModel('openai:gpt-4o-mini')
        })

        await waitFor(() => expect(result.current.modelKey).toBe('openai:gpt-4o-mini'))
        expect(setSessionModelMock).toHaveBeenCalledWith('thread-1', 'openai:gpt-4o-mini')
    })

    it('新会话先记在本地，落库后只补写一次', async () => {
        setSessionModelMock.mockResolvedValueOnce({ model_key: 'openai:gpt-4o-mini' })

        const { result, rerender } = renderHook(
            ({ isPersisted }: { isPersisted: boolean }) =>
                useChatModel({
                    threadId: 'thread-new',
                    isPersisted,
                    sessionModelKey: null,
                }),
            {
                wrapper: createWrapper(createClient(), true),
                initialProps: { isPersisted: false },
            },
        )

        await waitFor(() => expect(result.current.isAvailable).toBe(true))

        act(() => {
            result.current.setModel('openai:gpt-4o-mini')
        })
        expect(result.current.modelKey).toBe('openai:gpt-4o-mini')
        expect(setSessionModelMock).not.toHaveBeenCalled()

        rerender({ isPersisted: true })

        await waitFor(() => expect(setSessionModelMock).toHaveBeenCalledTimes(1))
        expect(setSessionModelMock).toHaveBeenCalledWith('thread-new', 'openai:gpt-4o-mini')
    })

    it('持久化失败时回滚到切换前的模型并提示', async () => {
        setSessionModelMock.mockRejectedValueOnce(new Error('boom'))

        const { result } = renderHook(
            () =>
                useChatModel({
                    threadId: 'thread-1',
                    isPersisted: true,
                    sessionModelKey: 'openai:gpt-4o',
                }),
            { wrapper: createWrapper(createClient()) },
        )

        await waitFor(() => expect(result.current.isAvailable).toBe(true))

        act(() => {
            result.current.setModel('openai:gpt-4o-mini')
        })

        await waitFor(() => expect(result.current.modelKey).toBe('openai:gpt-4o'))
        expect(toastErrorMock).toHaveBeenCalledTimes(1)
    })

    it('目录为空时隐藏选择器', async () => {
        catalogState.list = []

        const { result } = renderHook(
            () =>
                useChatModel({
                    threadId: 'thread-1',
                    isPersisted: true,
                    sessionModelKey: null,
                }),
            { wrapper: createWrapper(createClient()) },
        )

        await waitFor(() => expect(result.current.isLoading).toBe(false))
        expect(result.current.isAvailable).toBe(false)
        expect(result.current.models).toEqual([])
    })
})
