import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/core/http', () => ({
  http: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

import { http } from '@/core/http'

import {
  createModelConnection,
  deleteModelConnection,
  listModelConnections,
  listModels,
  verifyModelConnection,
} from './models'

describe('models api', () => {
  beforeEach(() => {
    vi.mocked(http.get).mockResolvedValue({ list: [], total: 0, page: 1, size: 100 })
    vi.mocked(http.post).mockResolvedValue({})
  })

  it('模型目录请求 v2 基址，失败时静默并取满服务端 100 条上限', async () => {
    await listModels()
    expect(http.get).toHaveBeenCalledWith('/models', {
      baseURL: '/api/v2',
      params: { page: 1, size: 100 },
      silent: true,
    })
  })

  it('BYOK 连接列表走 v2 基址分页，未启用时由调用方隐藏入口', async () => {
    await listModelConnections()
    expect(http.get).toHaveBeenCalledWith('/model-connections', {
      baseURL: '/api/v2',
      params: { page: 1, size: 100 },
      silent: true,
    })
  })

  it('创建连接提交 providerCode、baseUrl 与 apiKey', async () => {
    const payload = { providerCode: 'openai', baseUrl: null, apiKey: 'sk-test' }

    await createModelConnection(payload)
    expect(http.post).toHaveBeenCalledWith('/model-connections', payload)
  })

  it('校验连接时对 id 做 URL 编码', async () => {
    await verifyModelConnection('conn/1')
    expect(http.post).toHaveBeenCalledWith('/model-connections/conn%2F1/verify')
  })

  it('删除连接命中软删除端点', async () => {
    await deleteModelConnection('conn-1')
    expect(http.delete).toHaveBeenCalledWith('/model-connections/conn-1')
  })
})
