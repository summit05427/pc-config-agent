import { z } from 'zod'
import { httpJson, refreshAccessToken } from '@/core/http/client'
import { useAuthStore, type AuthUser } from '@/stores/auth-store'

/**
 * Java `/api/v1/auth/me` 与登录响应中的用户结构。
 * 服务端返回值先过 zod，避免字段变更悄悄流入页面。
 */
const authUserSchema = z.object({
  publicId: z.string().min(1),
  username: z.string().min(1),
  roles: z.array(z.string()),
})

const loginResponseSchema = z.object({
  accessToken: z.string().min(1),
  tokenType: z.string(),
  expiresIn: z.number(),
  user: authUserSchema,
})

export interface LoginResponse {
  accessToken: string
  tokenType: string
  expiresIn: number
  user: AuthUser
}

export interface LoginInput {
  username: string
  password: string
}

/** 账号密码登录；刷新令牌由服务端写入 HttpOnly Cookie，前端拿不到。 */
export async function loginWithPassword(
  input: LoginInput
): Promise<LoginResponse> {
  const payload = loginResponseSchema.parse(
    await httpJson<unknown>({ url: '/auth/login', method: 'post', data: input })
  )
  useAuthStore
    .getState()
    .auth.setSession({ user: payload.user, accessToken: payload.accessToken })
  return payload
}

/** 退出登录：服务端撤销刷新会话并清除 Cookie。 */
export async function logout(): Promise<void> {
  await httpJson<null>({ url: '/auth/logout', method: 'post' })
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  return authUserSchema.parse(
    await httpJson<unknown>({ url: '/auth/me', method: 'get' })
  )
}

/**
 * 守卫用的会话恢复。
 *
 * 页面刷新后内存令牌已丢失，这里用 HttpOnly 刷新 Cookie 换新令牌再拉取用户信息；
 * 任一环节失败都视为未登录，并清空本地会话。
 */
export async function ensureSession(): Promise<AuthUser | null> {
  const { accessToken, user } = useAuthStore.getState().auth
  if (accessToken && user) {
    return user
  }

  try {
    if (!accessToken && !(await refreshAccessToken())) {
      return null
    }
    const currentUser = await fetchCurrentUser()
    useAuthStore.getState().auth.setSession({
      user: currentUser,
      accessToken: useAuthStore.getState().auth.accessToken,
    })
    return currentUser
  } catch {
    useAuthStore.getState().auth.reset()
    return null
  }
}
