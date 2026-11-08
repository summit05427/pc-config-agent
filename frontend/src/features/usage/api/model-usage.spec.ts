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

import { getMyModelUsage } from './model-usage'

describe('usage api', () => {
  beforeEach(() => {
    vi.mocked(http.get).mockResolvedValue({ quota: {}, list: [], total: 0, page: 1, size: 20 })
  })

  it('查询用量时带分页与日期参数，并静默失败', async () => {
    const query = { page: 2, size: 10, from: '2026-10-01', to: '2026-10-31' }

    await getMyModelUsage(query)
    expect(http.get).toHaveBeenCalledWith('/users/me/model-usage', {
      params: query,
      silent: true,
    })
  })

  it('未传参数时使用空对象，避免把 undefined 写进 URL', async () => {
    await getMyModelUsage()
    expect(http.get).toHaveBeenCalledWith('/users/me/model-usage', {
      params: {},
      silent: true,
    })
  })
})
