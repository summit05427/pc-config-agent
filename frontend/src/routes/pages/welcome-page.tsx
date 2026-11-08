import { useTranslation } from 'react-i18next'
import { Link } from '@tanstack/react-router'
import { ArrowRight } from 'lucide-react'
import { LocaleToggle } from '@/app/layouts/components/locale-toggle'
import { ThemeToggle } from '@/app/layouts/components/theme-toggle'
import { UserMenu } from '@/app/layouts/components/user-menu'
import { ROUTE_PATHS } from '@/routes/paths'
import { env } from '@/shared/lib/env'
import { BrandMark } from '@/shared/ui/brand-mark'
import { Button } from '@/shared/ui/button'

/**
 * 欢迎页：公开入口，登录后才展示最近会话。
 *
 * 任务输入框属于对话批次，这里先保留建议清单作为「可以直接做什么」的示范，
 * 不放置无实际提交行为的假输入框。
 */
export function WelcomePage() {
  const { t } = useTranslation()

  return (
    <div className="flex h-dvh flex-col bg-canvas text-foreground">
      <header className="flex h-[var(--app-titlebar-height)] shrink-0 items-center gap-2 px-4 sm:px-6">
        <BrandMark size="md" />
        <span className="brand-wordmark">{env.title}</span>

        <div className="ml-auto flex items-center gap-0.5">
          <Button
            asChild
            variant="ghost"
            size="sm"
            className="mr-1 hidden text-muted-foreground sm:inline-flex"
          >
            <Link to={ROUTE_PATHS.chatNew}>
              {t('welcome.openWorkspace')}
              <ArrowRight className="size-3.5" />
            </Link>
          </Button>
          <ThemeToggle />
          <LocaleToggle />
          <UserMenu compact />
        </div>
      </header>
      <main></main>
    </div>
  )
}
