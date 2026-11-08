import { Ellipsis, LogIn, LogOut, Settings, UserRound } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'

import { useAppStore } from '@/app/stores/app-store'
import { useAuthSessionStore } from '@/features/auth/model/auth-session'
import { profileQueryOptions } from '@/features/settings/api/queries'
import { ROUTE_PATHS } from '@/routes/paths'
import { Button } from '@/shared/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/shared/ui/dropdown-menu'

export interface UserMenuProps {
  /** 仅显示头像按钮，用于顶栏与折叠侧栏 */
  compact?: boolean
}

/** 账户菜单：资料、设置与登出入口，是外壳里唯一的账户操作入口 */
export function UserMenu({ compact = false }: UserMenuProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const username = useAuthSessionStore((state) => state.user?.username ?? '')
  const isAuthenticated = useAuthSessionStore((state) => state.status === 'authenticated')
  const logout = useAuthSessionStore((state) => state.logout)
  // 箭头右侧菜单图标可由设置页开关隐藏，入口本身保持可点击
  const showAccountMenuIcon = useAppStore((state) => state.showAccountMenuIcon)
  // 登录接口只回用户名与角色，昵称与邮箱需要读资料接口；未登录时不发请求。
  // 账户入口在每个页面都挂载，给 5 分钟新鲜期避免切回窗口就重新拉一次。
  const { data: profile } = useQuery({
    ...profileQueryOptions,
    enabled: isAuthenticated,
    staleTime: 5 * 60_000,
  })

  // 优先展示资料里的昵称，未设置或资料尚未返回时回退登录账号
  const displayName =
    profile?.displayName?.trim() || username || t('settings.profile.guestName')
  const secondaryLine = profile?.email?.trim() || (isAuthenticated ? username : '')

  const initials = displayName.trim().slice(0, 2).toUpperCase()

  const handleLogout = async (): Promise<void> => {
    // 服务端撤销失败也会清理本地态，不阻断用户退出
    await logout()
    await navigate({ to: ROUTE_PATHS.login, replace: true })
  }

  const avatar = (
    <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/12 text-xs font-semibold text-primary">
      {initials ? initials : <UserRound className="size-3.5" aria-hidden="true" />}
    </span>
  )

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        {compact ? (
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('layout.account')}
            title={t('layout.account')}
          >
            {avatar}
          </Button>
        ) : (
          <Button
            variant="ghost"
            className="w-full justify-start gap-2.5 px-2 text-nav"
            aria-label={t('layout.account')}
          >
            {avatar}
            <span className="truncate">{displayName}</span>
            {showAccountMenuIcon ? (
              <Ellipsis className="ml-auto size-3.5 text-muted-foreground" aria-hidden="true" />
            ) : null}
          </Button>
        )}
      </DropdownMenuTrigger>

      <DropdownMenuContent
        align={compact ? 'start' : 'end'}
        side={compact ? 'right' : 'bottom'}
        className="min-w-52"
      >
        <DropdownMenuLabel className="font-normal">
          <span className="block truncate text-sm text-foreground">{displayName}</span>
          {secondaryLine ? (
            <span className="mt-0.5 block truncate text-xs text-muted-foreground">
              {secondaryLine}
            </span>
          ) : (
            <span className="mt-0.5 block text-xs text-muted-foreground">
              {t('settings.profile.notSignedIn')}
            </span>
          )}
        </DropdownMenuLabel>

        <DropdownMenuSeparator />

        <DropdownMenuItem onSelect={() => void navigate({ to: ROUTE_PATHS.settings })}>
          <Settings className="mr-2 size-4" aria-hidden="true" />
          {t('settings.menu.settings')}
        </DropdownMenuItem>

        <DropdownMenuSeparator />

        {isAuthenticated ? (
          <DropdownMenuItem onSelect={() => void handleLogout()}>
            <LogOut className="mr-2 size-4" aria-hidden="true" />
            {t('layout.logout')}
          </DropdownMenuItem>
        ) : (
          <DropdownMenuItem onSelect={() => void navigate({ to: ROUTE_PATHS.login })}>
            <LogIn className="mr-2 size-4" aria-hidden="true" />
            {t('layout.login')}
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
