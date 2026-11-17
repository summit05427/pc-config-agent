import { Link } from '@tanstack/react-router'

import { useAuthSessionStore } from '@/features/auth/model/auth-session'
import { ROUTE_PATHS } from '@/routes/paths'

export interface WelcomeExploreButtonProps {
  label: string
}

/** 白底胶囊 CTA：配色走落地页固定方案（近黑底 + 白底深字），不接主题令牌 */
export function WelcomeExploreButton({ label }: WelcomeExploreButtonProps) {
  // 登录态在此页可能仍是 unknown（由登录页守卫兜底判断 Cookie 会话），未确认时先去登录页
  const isAuthenticated = useAuthSessionStore((state) => state.status === 'authenticated')

  return (
    <Link
      to={isAuthenticated ? ROUTE_PATHS.chatNew : ROUTE_PATHS.login}
      className="inline-flex items-center justify-center rounded-xl bg-[#f5f5f5] px-5 py-2 text-sm font-medium text-[#111111] transition-transform duration-200 hover:scale-[1.03] active:scale-[0.98]"
    >
      {label}
    </Link>
  )
}
