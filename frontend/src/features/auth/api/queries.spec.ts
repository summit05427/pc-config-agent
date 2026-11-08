import { describe, expect, it } from 'vitest'

import { queryKeys } from '@/shared/lib/query-keys'

import { currentUserQueryOptions } from './queries'

describe('currentUserQueryOptions', () => {
  it('使用集中登记的 queryKey，避免出现第二个缓存来源', () => {
    expect(currentUserQueryOptions.queryKey).toEqual(queryKeys.auth.currentUser)
  })

  it('查询函数直接复用认证 API', () => {
    expect(currentUserQueryOptions.staleTime).toBe(5 * 60 * 1000)
    expect(typeof currentUserQueryOptions.queryFn).toBe('function')
  })
})
