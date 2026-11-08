import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/features/auth/api', () => ({
  getCurrentUser: vi.fn(),
  login: vi.fn(),
  logoutSession: vi.fn(),
  refreshSession: vi.fn(),
}))

import {
  getCurrentUser,
  login as loginApi,
  logoutSession,
  refreshSession as refreshSessionApi,
  type RefreshResult,
  type CurrentUser,
} from '@/features/auth/api'
import {
  ensureAuthSession,
  selectIsAuthenticated,
  selectUsername,
  useAuthSessionStore,
} from '@/features/auth/model/auth-session'
import {
  acceptToken,
  configureAuth,
  getAccessToken,
  resetAuthForTests,
} from '@/core/http'

const currentUser: CurrentUser = {
  publicId: 'u-1',
  username: 'tester',
  roles: ['USER'],
}

const refreshResult: RefreshResult = {
  accessToken: 'token-1',
  tokenType: 'Bearer',
  expiresIn: 900,
}

describe('auth session', () => {
  beforeEach(() => {
    useAuthSessionStore.setState({ status: 'unknown', user: null })
    resetAuthForTests()
    // 与 main.tsx 的装配保持一致：刷新走 store，跳转在测试里不需要
    configureAuth({
      refresh: () => useAuthSessionStore.getState().refreshSessionToken(),
      onUnauthorized: () => undefined,
    })
    vi.mocked(refreshSessionApi).mockReset()
    vi.mocked(getCurrentUser).mockReset()
    vi.mocked(loginApi).mockReset()
    vi.mocked(logoutSession).mockReset()
  })

  it('并发恢复只刷新一次 Cookie 会话并写入用户资料', async () => {
    vi.mocked(refreshSessionApi).mockResolvedValue(refreshResult)
    vi.mocked(getCurrentUser).mockResolvedValue(currentUser)

    const results = await Promise.all([ensureAuthSession(), ensureAuthSession()])

    expect(refreshSessionApi).toHaveBeenCalledTimes(1)
    expect(getCurrentUser).toHaveBeenCalledTimes(1)
    expect(results).toEqual([true, true])

    const state = useAuthSessionStore.getState()
    expect(state.status).toBe('authenticated')
    expect(state.user).toEqual(currentUser)
    expect(selectIsAuthenticated(state)).toBe(true)
    expect(selectUsername(state)).toBe('tester')
    expect(getAccessToken()).toBe('token-1')
  })

  it('刷新失败时清空登录态并返回未登录', async () => {
    vi.mocked(refreshSessionApi).mockRejectedValue(new Error('cookie expired'))
    acceptToken('stale-token')

    const state = useAuthSessionStore.getState()
    await expect(state.restoreSession()).resolves.toBe(false)

    expect(useAuthSessionStore.getState().status).toBe('unauthenticated')
    expect(useAuthSessionStore.getState().user).toBeNull()
    expect(getAccessToken()).toBe('')
  })

  it('已确认未登录后不再重复请求刷新', async () => {
    useAuthSessionStore.setState({ status: 'unauthenticated', user: null })

    await expect(ensureAuthSession()).resolves.toBe(false)
    expect(refreshSessionApi).not.toHaveBeenCalled()
  })

  it('登录成功后写入内存 Token 与用户资料', async () => {
    vi.mocked(loginApi).mockResolvedValue({
      ...refreshResult,
      user: currentUser,
    })

    await useAuthSessionStore.getState().login({ username: 'tester', password: 'secret' })

    expect(loginApi).toHaveBeenCalledWith({ username: 'tester', password: 'secret' })
    expect(useAuthSessionStore.getState().status).toBe('authenticated')
    expect(useAuthSessionStore.getState().user).toEqual(currentUser)
    expect(getAccessToken()).toBe('token-1')
  })

  it('退出登录时服务端失败也清理本地态', async () => {
    acceptToken('token-1')
    useAuthSessionStore.setState({ status: 'authenticated', user: currentUser })
    vi.mocked(logoutSession).mockRejectedValue(new Error('network'))

    await useAuthSessionStore.getState().logout()

    expect(useAuthSessionStore.getState().status).toBe('unauthenticated')
    expect(getAccessToken()).toBe('')
  })

  it('登出后到达的刷新结果被丢弃，不写回旧令牌', async () => {
    let resolveRefresh: ((value: RefreshResult) => void) | undefined
    vi.mocked(refreshSessionApi).mockImplementation(
      () =>
        new Promise<RefreshResult>((resolve) => {
          resolveRefresh = resolve
        }),
    )

    const pendingToken = useAuthSessionStore.getState().refreshSessionToken()
    useAuthSessionStore.getState().clearSession()
    resolveRefresh?.(refreshResult)

    await expect(pendingToken).resolves.toBeNull()
    expect(getAccessToken()).toBe('')
  })
})
