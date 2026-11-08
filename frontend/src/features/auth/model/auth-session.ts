import { create } from 'zustand'
import { immer } from 'zustand/middleware/immer'

import { acceptToken, clearToken, refreshOnce } from '@/core/http'

import {
  getCurrentUser,
  login as loginApi,
  logoutSession,
  refreshSession as refreshSessionApi,
  type CurrentUser,
  type LoginParams,
} from '@/features/auth/api'

/**
 * 登录态四态。
 *
 * `unknown` 表示尚未确认：刷新页面后本地没有任何凭证，只能靠 HttpOnly Cookie
 * 调 /auth/refresh 才能判断；此时不应把用户当作未登录直接跳登录页。
 */
export type AuthStatus = 'unknown' | 'refreshing' | 'authenticated' | 'unauthenticated'

export interface AuthSessionState {
  status: AuthStatus
  user: CurrentUser | null
  login: (params: LoginParams) => Promise<void>
  logout: () => Promise<void>
  /** 启动或路由守卫触发：用 Cookie 换取 Token 后回读用户资料 */
  restoreSession: () => Promise<boolean>
  clearSession: () => void
  /** 由请求层单飞调用，成功返回新 Token，失败返回 null */
  refreshSessionToken: () => Promise<string | null>
}

export const selectIsAuthenticated = (state: AuthSessionState): boolean =>
  state.status === 'authenticated'

export const selectIsRefreshing = (state: AuthSessionState): boolean =>
  state.status === 'refreshing'

export const selectUsername = (state: AuthSessionState): string => state.user?.username ?? ''

export const selectRoles = (state: AuthSessionState): string[] => state.user?.roles ?? []

// 会话代次：登出后到达的刷新结果必须丢弃，否则会把旧令牌写回内存
let sessionEpoch = 0
// 启动恢复只允许并发一次，避免多个路由守卫同时打 /auth/refresh
let restorePromise: Promise<boolean> | null = null

export const useAuthSessionStore = create<AuthSessionState>()(
  // immer 中间件让 set 支持 mutate 写法；此处仍用局部对象覆盖，保持登录态更新语义直白
  immer((set, get) => {
    const applySession = (accessToken: string, user: CurrentUser): void => {
      // acceptToken 同时重置 401 单飞标记，新会话允许下一次 401 再次触发跳转
      acceptToken(accessToken)
      set({ user, status: 'authenticated' })
    }

    const clearSession = (): void => {
      sessionEpoch += 1
      // clearToken 同时丢弃进行中的刷新，避免旧令牌回写
      clearToken()
      set({ user: null, status: 'unauthenticated' })
    }

    const refreshSessionToken = async (): Promise<string | null> => {
      const epoch = sessionEpoch
      try {
        const result = await refreshSessionApi()
        if (epoch !== sessionEpoch) {
          return null
        }
        acceptToken(result.accessToken)
        return result.accessToken
      } catch {
        return null
      }
    }

    const restoreSession = async (): Promise<boolean> => {
      if (get().status === 'authenticated') {
        return true
      }
      if (restorePromise) {
        return restorePromise
      }

      set({ status: 'refreshing' })
      restorePromise = (async () => {
        try {
          const token = await refreshOnce()
          if (!token) {
            throw new Error('refresh unavailable')
          }
          const currentUser = await getCurrentUser()
          applySession(token, currentUser)
          return true
        } catch {
          // 刷新失败等同于未登录，由路由守卫跳转登录页
          clearSession()
          return false
        } finally {
          restorePromise = null
        }
      })()

      return restorePromise
    }

    const login = async (params: LoginParams): Promise<void> => {
      const result = await loginApi(params)
      applySession(result.accessToken, result.user)
    }

    /**
     * 退出登录：先撤销服务端会话，再清理本地状态。
     *
     * 网络失败时仍清本地态，否则用户会被卡在已登录界面却无法重试退出。
     */
    const logout = async (): Promise<void> => {
      try {
        await logoutSession()
      } catch {
        // 服务端撤销失败不阻断本地退出；Cookie 由服务端的清空响应兜底
      } finally {
        clearSession()
      }
    }

    return {
      status: 'unknown',
      user: null,
      login,
      logout,
      restoreSession,
      clearSession,
      refreshSessionToken,
    }
  }),
)

/**
 * 路由守卫与启动逻辑共用的入口。
 *
 * 与 Vue 基线一致：只有 `unknown` 才尝试用 Cookie 恢复；一旦确认未登录，
 * 后续导航不再重复请求 /auth/refresh，避免守卫链上产生多次刷新。
 */
export const ensureAuthSession = (): Promise<boolean> => {
  const state = useAuthSessionStore.getState()

  if (state.status === 'authenticated') {
    return Promise.resolve(true)
  }
  if (state.status === 'unauthenticated') {
    return Promise.resolve(false)
  }

  return state.restoreSession()
}
