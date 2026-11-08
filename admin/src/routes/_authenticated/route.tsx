import { createFileRoute, redirect } from '@tanstack/react-router'
import { ensureSession } from '@/features/auth/api/auth-api'
import { hasRole } from '@/stores/auth-store'
import { AuthenticatedLayout } from '@/components/layout/authenticated-layout'

/**
 * 管理端统一入口守卫。
 *
 * 未登录时先尝试用 HttpOnly 刷新 Cookie 恢复会话；恢复失败跳登录页并记录回跳地址。
 * 已登录但不是 ADMIN 的用户访问 `/403`，避免绕过页面按钮直接猜 URL 访问管理接口。
 */
export const Route = createFileRoute('/_authenticated')({
  beforeLoad: async ({ location }) => {
    const user = await ensureSession()
    if (!user) {
      throw redirect({
        to: '/sign-in',
        search: { redirect: location.href },
      })
    }
    if (!hasRole(user, 'ADMIN')) {
      throw redirect({ to: '/403' })
    }
  },
  component: AuthenticatedLayout,
})
