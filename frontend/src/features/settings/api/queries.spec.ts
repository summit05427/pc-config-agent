import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/features/auth/api', () => ({
  getProfile: vi.fn(),
  listDeviceSessions: vi.fn(),
}))

vi.mock('./preferences', () => ({
  getPreferences: vi.fn(),
}))

import {
  getProfile,
  listDeviceSessions,
  type DeviceSessionSummary,
  type UserProfile,
} from '@/features/auth/api'
import { queryKeys } from '@/shared/lib/query-keys'
import type { PageResult } from '@/shared/types/http'

import { getPreferences, type UserPreferences } from './preferences'
import { deviceSessionsQueryOptions, preferencesQueryOptions, profileQueryOptions } from './queries'

// queryOptions 的 queryFn 在类型上是可选的联合类型，测试里已确认存在，直接收窄成无参函数
const runQuery = <T>(queryFn: unknown): Promise<T> => (queryFn as () => Promise<T>)()

const PREFERENCES: UserPreferences = {
  instructions: null,
  replyLanguage: 'auto',
  responseStyle: 'balanced',
  useHistory: true,
  updatedAt: null,
}

const PROFILE: UserProfile = {
  publicId: 'user-1',
  username: 'tester',
  displayName: null,
  email: null,
  bio: null,
  roles: ['USER'],
  status: 'ACTIVE',
  createdAt: '2026-10-01T08:00:00Z',
  updatedAt: '2026-10-01T08:00:00Z',
}

const DEVICES: PageResult<DeviceSessionSummary> = {
  list: [
    {
      familyId: 'family-1',
      createdAt: '2026-10-01T08:00:00Z',
      lastUsedAt: null,
      idleExpiresAt: '2026-10-08T08:00:00Z',
      absoluteExpiresAt: '2026-11-01T08:00:00Z',
      current: true,
    },
  ],
  total: 1,
  page: 2,
  size: 10,
}

beforeEach(() => {
  vi.mocked(getPreferences).mockResolvedValue(PREFERENCES)
  vi.mocked(getProfile).mockResolvedValue(PROFILE)
  vi.mocked(listDeviceSessions).mockResolvedValue(DEVICES)
})

describe('settings queryOptions', () => {
  it('偏好查询复用集中登记的 key，并直接返回服务端偏好', async () => {
    expect(preferencesQueryOptions.queryKey).toEqual(queryKeys.settings.preferences)

    await expect(runQuery<UserPreferences>(preferencesQueryOptions.queryFn)).resolves.toEqual(
      PREFERENCES,
    )
    expect(getPreferences).toHaveBeenCalledOnce()
  })

  it('资料查询与保存后的失效 key 一致', async () => {
    expect(profileQueryOptions.queryKey).toEqual(queryKeys.settings.profile)

    await expect(runQuery<UserProfile>(profileQueryOptions.queryFn)).resolves.toEqual(PROFILE)
    expect(getProfile).toHaveBeenCalledOnce()
  })

  it('设备列表复用统一 key，并一次取满后端上限', async () => {
    const options = deviceSessionsQueryOptions()

    expect(options.queryKey).toEqual(queryKeys.settings.deviceSessionsAll)

    await expect(runQuery<PageResult<DeviceSessionSummary>>(options.queryFn)).resolves.toEqual(
      DEVICES,
    )
    expect(listDeviceSessions).toHaveBeenCalledWith({ page: 1, size: 100 })
  })

  it('服务端失败时错误透传给调用方，交给 Query 与页面统一处理', async () => {
    vi.mocked(getProfile).mockRejectedValueOnce(new Error('资料读取失败'))

    await expect(runQuery<UserProfile>(profileQueryOptions.queryFn)).rejects.toThrow('资料读取失败')
  })
})
