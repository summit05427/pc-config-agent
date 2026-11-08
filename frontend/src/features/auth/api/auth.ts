import { http } from '@/core/http'

export interface LoginParams {
  username: string
  password: string
}

export interface CurrentUser {
  /** 对外身份标识（UUID），内部自增主键不出现在任何响应里 */
  publicId: string
  username: string
  roles: string[]
}

export interface LoginResult {
  accessToken: string
  tokenType: string
  expiresIn: number
  /** 登录响应同时带回用户信息，前端无需再额外请求一次 /auth/me */
  user: CurrentUser
}

export interface RefreshResult {
  accessToken: string
  tokenType: string
  expiresIn: number
}

// 路径只写服务内相对路径，/api/v1 前缀由 VITE_API_BASE_URL 提供
export const login = (params: LoginParams): Promise<LoginResult> =>
  http.post<LoginResult>('/auth/login', params, { authPolicy: 'no-redirect' })

/**
 * 用 HttpOnly Cookie 换取新的 Access Token。
 *
 * 刷新令牌不经过 JS，同源部署下浏览器会自动携带 Cookie；
 * 若未来改为跨域部署，需要在请求层显式开启 withCredentials。
 */
export const refreshSession = (): Promise<RefreshResult> =>
  http.post<RefreshResult>('/auth/refresh', undefined, { authPolicy: 'no-redirect' })

/** 撤销当前刷新会话并清 Cookie；未登录时调用同样返回成功 */
export const logoutSession = (): Promise<void> =>
  http.post<void>('/auth/logout', undefined, { authPolicy: 'no-refresh' })

/**
 * 退出所有设备：撤销该账号全部刷新会话，服务端同时清除当前 Cookie。
 *
 * 需要有效的 Access Token（不走 Cookie），因此即使 Cookie 已失效也能成功。
 */
export const logoutAllSessions = (): Promise<void> =>
  http.post<void>('/auth/logout-all', undefined, { authPolicy: 'no-refresh' })

/** 刷新页面后用 Token 换回用户名与角色，避免把用户资料长期落在浏览器里 */
export const getCurrentUser = (): Promise<CurrentUser> => http.get<CurrentUser>('/auth/me')
