import type { QueryClient } from '@tanstack/react-query'
import { redirect, type ParsedLocation } from '@tanstack/react-router'

import { currentUserQueryOptions } from '@/features/auth/api'
import { ensureAuthSession } from '@/features/auth/model/auth-session'

import { ROUTE_PATHS } from './paths'

export interface RouterContext {
  queryClient: QueryClient
}

interface GuardArgs {
  context: RouterContext
  location: ParsedLocation
}

/**
 * 受保护路由守卫。
 *
 * 首次导航先确认登录态：Access Token 只在内存里，刷新页面后只有 HttpOnly Cookie
 * 能证明会话仍有效，不能直接把 unknown 当作未登录。
 * 登录成功后再用 ensureQueryData 预热当前用户，保证页面与请求层共用同一份缓存，
 * Loader 内不直接发 HTTP，也不产生第二份缓存。
 */
export const requireAuthenticated = async ({ context, location }: GuardArgs): Promise<void> => {
  const isAuthenticated = await ensureAuthSession()

  if (!isAuthenticated) {
    throw redirect({ to: ROUTE_PATHS.login, search: { redirect: location.href } })
  }

  await context.queryClient.ensureQueryData(currentUserQueryOptions)
}

/** 已登录用户不再停留在登录页，直接进入新对话页 */
export const redirectAuthenticatedUser = async (): Promise<void> => {
  const isAuthenticated = await ensureAuthSession()

  if (isAuthenticated) {
    throw redirect({ to: ROUTE_PATHS.chatNew, replace: true })
  }
}
