import { env } from '@/lib/env'

/**
 * 校验登录后的跳转目标。
 *
 * 只接受站内绝对路径，拒绝 `//evil.example` 这类协议相对地址，避免开放重定向。
 * 部署在 `/admin/` 时，浏览器原始地址可能带前缀，但 Router 的 `to` 不需要前缀，这里统一剥掉。
 */
export function resolveSafeRedirect(
  target: string | undefined,
  fallback = '/users'
): string {
  if (!target) return fallback
  if (!target.startsWith('/') || target.startsWith('//')) return fallback

  const basePath = env.routerBasePath
  if (
    basePath &&
    (target === basePath || target.startsWith(`${basePath}/`))
  ) {
    return target.slice(basePath.length) || '/'
  }
  return target
}
