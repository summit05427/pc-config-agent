import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/core/http'

import { useModelConnectionCreate, useModelConnections } from './use-model-connections'

const { verifyMock, removeMock, rotateMock, createMock, toastSuccessMock, queryState } = vi.hoisted(
  () => ({
    verifyMock: vi.fn(),
    removeMock: vi.fn(),
    rotateMock: vi.fn(),
    createMock: vi.fn(),
    toastSuccessMock: vi.fn(),
    // 供应商目录查询的错误开关：用于区分「未启用」与「加载失败」
    queryState: { providerError: null as Error | null },
  }),
)

const catalog = [
  {
    provider: 'openai',
    modelKey: 'openai:gpt-4o',
    displayName: 'GPT-4o',
    capabilities: ['text', 'vision'],
    contextWindow: 128000,
  },
]

const connection = {
  id: 'conn-1',
  provider: 'openai',
  providerName: 'OpenAI',
  baseUrl: 'https://api.openai.com/v1',
  status: 'ACTIVE',
  lastVerifiedAt: null,
  createdAt: '2026-10-30T08:00:00Z',
  credential: null,
}

const providers = [
  { code: 'openai', displayName: 'OpenAI', protocol: 'openai', defaultBaseUrl: null, modelCount: 1 },
  { code: 'deepseek', displayName: 'DeepSeek', protocol: 'openai', defaultBaseUrl: null, modelCount: 2 },
]

vi.mock('sonner', () => ({ toast: { success: toastSuccessMock } }))

// key 与 shared/lib/query-keys 保持一致；queryKeys 是外部模块，不能在 hoisted 工厂里引用
vi.mock('@/features/models/api', () => {
  const page = <T,>(list: T[]) => ({ list, total: list.length, page: 1, size: 100 })

  return {
    modelCatalogQueryOptions: {
      queryKey: ['models', 'catalog'],
      queryFn: () => Promise.resolve(page(catalog)),
    },
    modelConnectionsQueryOptions: {
      queryKey: ['models', 'connections'],
      queryFn: () => Promise.resolve(page([connection])),
    },
    modelProvidersQueryOptions: {
      queryKey: ['models', 'providers'],
      queryFn: () =>
        queryState.providerError
          ? Promise.reject(queryState.providerError)
          : Promise.resolve(providers),
    },
    // useMutation 会额外传入 context，这里包一层只保留业务参数，断言更精确
    verifyModelConnection: (connectionId: string) => verifyMock(connectionId),
    deleteModelConnection: (connectionId: string) => removeMock(connectionId),
    updateModelConnection: (connectionId: string, payload: unknown) =>
      rotateMock(connectionId, payload),
    createModelConnection: (payload: unknown) => createMock(payload),
  }
})

function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

function renderModelHook<T>(hook: () => T, queryClient: QueryClient) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  return renderHook(hook, { wrapper })
}

describe('useModelConnections', () => {
  beforeEach(() => {
    queryState.providerError = null
  })

  it('把三份查询收敛为视图可用的派生数据', async () => {
    const { result } = renderModelHook(() => useModelConnections(), createQueryClient())

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.providerCodes).toEqual(['openai', 'deepseek'])
    expect(result.current.modelCounts.get('deepseek')).toBe(2)
    expect(result.current.configuredProviderCodes.has('openai')).toBe(true)
    expect(result.current.connections).toHaveLength(1)
  })

  it('验证成功后只失效连接列表并提示', async () => {
    const queryClient = createQueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    verifyMock.mockResolvedValueOnce(connection)

    const { result } = renderModelHook(() => useModelConnections(), queryClient)
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.verify('conn-1')
    })

    expect(verifyMock).toHaveBeenCalledWith('conn-1')
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['models', 'connections'] })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ['models', 'catalog'] })
    expect(toastSuccessMock).toHaveBeenCalledTimes(1)
  })

  it('删除成功同时失效连接列表与模型目录', async () => {
    const queryClient = createQueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    removeMock.mockResolvedValueOnce(undefined)

    const { result } = renderModelHook(() => useModelConnections(), queryClient)
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.remove('conn-1')
    })

    expect(removeMock).toHaveBeenCalledWith('conn-1')
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['models', 'connections'] })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['models', 'catalog'] })
  })

  it('轮换失败时把错误抛回调用方且不提示成功', async () => {
    rotateMock.mockRejectedValueOnce(new ApiError('密钥无效', { code: 40211, status: 400 }))

    const { result } = renderModelHook(() => useModelConnections(), createQueryClient())
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await expect(
      result.current.rotate('conn-1', { apiKey: 'sk-rotated-123456' }),
    ).rejects.toThrow('密钥无效')
    expect(rotateMock).toHaveBeenCalledWith('conn-1', { apiKey: 'sk-rotated-123456' })
    expect(toastSuccessMock).not.toHaveBeenCalled()
  })

  it('操作进行中记录忙碌连接 id，完成后清空', async () => {
    let resolveVerify: (value: unknown) => void = () => {}
    verifyMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveVerify = resolve
        }),
    )

    const { result } = renderModelHook(() => useModelConnections(), createQueryClient())
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    let verifyPromise: Promise<void> = Promise.resolve()
    act(() => {
      verifyPromise = result.current.verify('conn-1')
    })

    await waitFor(() => expect(result.current.busyConnectionId).toBe('conn-1'))

    resolveVerify(connection)
    await act(async () => {
      await verifyPromise
    })
    await waitFor(() => expect(result.current.busyConnectionId).toBeNull())
  })

  it('全部查询都返回未启用业务码时才降级为不可用', async () => {
    queryState.providerError = new ApiError('byok disabled', { code: 40209, status: 404 })

    const { result } = renderModelHook(() => useModelConnections(), createQueryClient())

    await waitFor(() => expect(result.current.isUnavailable).toBe(true))
    expect(result.current.isLoadError).toBe(false)
  })

  it('普通服务端错误按加载失败处理，不能误报为未启用', async () => {
    queryState.providerError = new ApiError('boom', { code: 500, status: 500 })

    const { result } = renderModelHook(() => useModelConnections(), createQueryClient())

    await waitFor(() => expect(result.current.isLoadError).toBe(true))
    expect(result.current.isUnavailable).toBe(false)
  })
})

describe('useModelConnectionCreate', () => {
  it('创建成功后失效连接与模型目录并提示', async () => {
    const queryClient = createQueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    createMock.mockResolvedValueOnce(connection)

    const { result } = renderModelHook(() => useModelConnectionCreate(), queryClient)

    await act(async () => {
      await result.current.create({ providerCode: 'openai', apiKey: 'sk-test-123456' })
    })

    expect(createMock).toHaveBeenCalledWith({
      providerCode: 'openai',
      apiKey: 'sk-test-123456',
    })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['models', 'connections'] })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['models', 'catalog'] })
    expect(toastSuccessMock).toHaveBeenCalledTimes(1)
  })
})
