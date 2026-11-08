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

import { getCurrentUser, login, logoutAllSessions, logoutSession, refreshSession } from './auth'

describe('auth api', () => {
  const loginResult = {
    accessToken: 'token-1',
    tokenType: 'Bearer',
    expiresIn: 900,
    user: { publicId: 'u-1', username: 'tester', roles: ['USER'] },
  }

  beforeEach(() => {
    vi.mocked(http.post).mockResolvedValue(loginResult)
    vi.mocked(http.get).mockResolvedValue(loginResult.user)
  })

  it('登录向 /auth/login 提交用户名与密码', async () => {
    await expect(login({ username: 'tester', password: 'secret' })).resolves.toEqual(loginResult)
    expect(http.post).toHaveBeenCalledWith(
      '/auth/login',
      { username: 'tester', password: 'secret' },
      { authPolicy: 'no-redirect' },
    )
  })

  it('刷新与退出登录命中对应端点', async () => {
    await refreshSession()
    await logoutSession()
    await logoutAllSessions()

    expect(vi.mocked(http.post).mock.calls.map((call) => call[0])).toEqual([
      '/auth/refresh',
      '/auth/logout',
      '/auth/logout-all',
    ])
  })

  it('读取当前用户命中 /auth/me', async () => {
    await expect(getCurrentUser()).resolves.toEqual(loginResult.user)
    expect(http.get).toHaveBeenCalledWith('/auth/me')
  })
})
