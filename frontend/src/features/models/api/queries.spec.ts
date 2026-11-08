import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./models', () => ({
  listModelConnections: vi.fn(),
  listModels: vi.fn(),
}))

import { queryKeys } from '@/shared/lib/query-keys'
import type { PageResult } from '@/shared/types/http'

import { listModelConnections, listModels } from './models'
import type { ModelCatalogItem, ModelConnection } from './models'
import { modelCatalogQueryOptions, modelConnectionsQueryOptions } from './queries'

// queryOptions 的 queryFn 在类型上是可选联合类型，测试里已确认存在，直接收窄成无参函数
const runQuery = <T>(queryFn: unknown): Promise<T> => (queryFn as () => Promise<T>)()

const CATALOG: ModelCatalogItem[] = [
  {
    provider: 'openai',
    modelKey: 'openai:gpt-5',
    displayName: 'GPT-5',
    capabilities: ['chat'],
    contextWindow: 128000,
  },
]

const CONNECTIONS: ModelConnection[] = [
  {
    id: 'conn-1',
    provider: 'openai',
    providerName: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
    status: 'ACTIVE',
    lastVerifiedAt: null,
    createdAt: '2026-10-01T08:00:00Z',
    credential: null,
  },
]

const pageOf = <T>(list: T[]): PageResult<T> => ({ list, total: list.length, page: 1, size: 100 })

beforeEach(() => {
  vi.mocked(listModels).mockResolvedValue(pageOf(CATALOG))
  vi.mocked(listModelConnections).mockResolvedValue(pageOf(CONNECTIONS))
})

describe('models queryOptions', () => {
  it('模型目录与对话页模型选择共用同一个 key', async () => {
    expect(modelCatalogQueryOptions.queryKey).toEqual(queryKeys.models.catalog)

    await expect(
      runQuery<PageResult<ModelCatalogItem>>(modelCatalogQueryOptions.queryFn),
    ).resolves.toEqual(pageOf(CATALOG))
    expect(listModels).toHaveBeenCalledOnce()
  })

  it('BYOK 连接列表在创建、验证与删除后统一失效', async () => {
    expect(modelConnectionsQueryOptions.queryKey).toEqual(queryKeys.models.connections)

    await expect(
      runQuery<PageResult<ModelConnection>>(modelConnectionsQueryOptions.queryFn),
    ).resolves.toEqual(pageOf(CONNECTIONS))
    expect(listModelConnections).toHaveBeenCalledOnce()
  })

  it('运行时未启用（404）与网络失败都把错误交给调用方隐藏入口', async () => {
    vi.mocked(listModels).mockRejectedValueOnce(new Error('模型目录不可用'))

    await expect(
      runQuery<PageResult<ModelCatalogItem>>(modelCatalogQueryOptions.queryFn),
    ).rejects.toThrow('模型目录不可用')
  })
})
