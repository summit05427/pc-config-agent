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
  changePassword,
  getProfile,
  listDeviceSessions,
  revokeDeviceSession,
  updateProfile,
} from './user'

describe('user api', () => {
  beforeEach(() => {
    vi.mocked(http.get).mockResolvedValue({ list: [], total: 0, page: 1, size: 20 })
    vi.mocked(http.put).mockResolvedValue({})
  })

  it('读取资料命中 /users/me/profile', async () => {
    await getProfile()
    expect(http.get).toHaveBeenCalledWith('/users/me/profile')
  })

  it('更新资料以 PUT 全量提交', async () => {
    const payload = { displayName: '张三', email: null, bio: '你好' }

    await updateProfile(payload)
    expect(http.put).toHaveBeenCalledWith('/users/me/profile', payload)
  })

  it('修改密码命中 /users/me/password', async () => {
    const payload = { currentPassword: 'old-pass', newPassword: 'new-pass' }

    await changePassword(payload)
    expect(http.put).toHaveBeenCalledWith('/users/me/password', payload)
  })

  it('登录设备列表按分页参数查询', async () => {
    await listDeviceSessions({ page: 2, size: 10 })
    expect(http.get).toHaveBeenCalledWith('/users/me/sessions', {
      params: { page: 2, size: 10 },
    })
  })

  it('撤销设备时对 familyId 做 URL 编码', async () => {
    await revokeDeviceSession('family/with space')
    expect(http.delete).toHaveBeenCalledWith('/users/me/sessions/family%2Fwith%20space')
  })
})
