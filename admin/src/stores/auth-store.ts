import { create } from 'zustand'

/**
 * 当前登录用户的最小信息，与 Java `/auth/me` 的响应保持一致。
 */
export interface AuthUser {
  publicId: string
  username: string
  roles: string[]
}

interface AuthState {
  auth: {
    user: AuthUser | null
    accessToken: string
    setSession: (session: { user: AuthUser; accessToken: string }) => void
    setAccessToken: (accessToken: string) => void
    setUser: (user: AuthUser) => void
    reset: () => void
  }
}

/**
 * 认证会话只存内存。
 *
 * 访问令牌属于短期凭证，放 Cookie/localStorage 会被 XSS 直接读取；
 * 页面刷新后由 HttpOnly 刷新 Cookie 换新令牌（见 core/http/client）。
 */
export const useAuthStore = create<AuthState>()((set) => ({
  auth: {
    user: null,
    accessToken: '',
    setSession: ({ user, accessToken }) =>
      set((state) => ({ auth: { ...state.auth, user, accessToken } })),
    setAccessToken: (accessToken) =>
      set((state) => ({ auth: { ...state.auth, accessToken } })),
    setUser: (user) => set((state) => ({ auth: { ...state.auth, user } })),
    reset: () =>
      set((state) => ({
        auth: { ...state.auth, user: null, accessToken: '' },
      })),
  },
}))

/** 判断当前用户是否具备某个角色，供路由守卫与按钮显隐复用。 */
export function hasRole(user: AuthUser | null, role: string): boolean {
  return user?.roles.includes(role) ?? false
}
