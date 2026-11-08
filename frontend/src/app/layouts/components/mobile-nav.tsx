import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams, useRouterState } from '@tanstack/react-router'
import { createPortal } from 'react-dom'
import { Plus, X } from 'lucide-react'

import { useAppStore } from '@/app/stores/app-store'
import { SettingsNav } from '@/features/settings/components/settings-nav'
import { resolveSettingsSection } from '@/features/settings/model/settings-sections'
import { ROUTE_PATHS } from '@/routes/paths'
import { Button } from '@/shared/ui/button'

import type { SidebarMode } from '../lib/nav'
import { AppLogo } from './app-logo'
import { SidebarSessionList } from './sidebar-session-list'
import { UserMenu } from './user-menu'

export interface MobileNavProps {
    /** 设置模式下抽屉内容整体替换为设置目录 */
    mode?: SidebarMode
}

/**
 * 窄屏导航抽屉。
 *
 * 关闭动作有三个来源：遮罩点击、关闭按钮、路由变化。打开后把焦点移到关闭按钮，
 * 保证键盘用户不会继续操作被遮挡的页面。
 */
export function MobileNav({ mode = 'default' }: MobileNavProps) {
    const { t } = useTranslation()
    const isOpen = useAppStore((state) => state.isMobileNavOpen)
    const closeMobileNav = useAppStore((state) => state.closeMobileNav)
    const pathname = useRouterState({ select: (state) => state.location.pathname })
    const params = useParams({ strict: false })
    const activeSection = resolveSettingsSection(params.section)
    const closeButtonRef = useRef<HTMLButtonElement | null>(null)

    // 移动端跳转后自动收起抽屉，避免遮挡新页面
    useEffect(() => {
        closeMobileNav()
    }, [pathname, closeMobileNav])

    useEffect(() => {
        if (!isOpen) {
            return
        }

        closeButtonRef.current?.focus()

        const handleEscape = (event: KeyboardEvent): void => {
            if (event.key === 'Escape') {
                closeMobileNav()
            }
        }

        window.addEventListener('keydown', handleEscape)
        return () => window.removeEventListener('keydown', handleEscape)
    }, [isOpen, closeMobileNav])

    if (!isOpen) {
        return null
    }

    return createPortal(
        <div className="fixed inset-0 z-50 md:hidden">
            <div className="absolute inset-0 bg-black/45" aria-hidden="true" onClick={closeMobileNav} />

            <aside
                role="dialog"
                aria-modal="true"
                aria-label={t('layout.navigation')}
                className="absolute inset-y-0 left-0 flex w-[min(var(--app-sidebar-width),85vw)] flex-col border-r border-sidebar-border bg-sidebar"
            >
                <div className="flex h-[var(--app-titlebar-height)] items-center justify-between gap-2 px-3">
                    <AppLogo />
                    <Button
                        ref={closeButtonRef}
                        variant="ghost"
                        size="icon-sm"
                        aria-label={t('layout.closeNav')}
                        onClick={closeMobileNav}
                    >
                        <X className="size-4" />
                    </Button>
                </div>

                {mode === 'settings' ? (
                    <SettingsNav activeSection={activeSection} onNavigate={closeMobileNav} />
                ) : (
                    <>
                        <div className="px-2 pb-1">
                            <Link
                                to={ROUTE_PATHS.chatNew}
                                className="flex h-[var(--app-sidebar-row-height)] w-full items-center gap-2 rounded-[var(--cds-radius-btn-xs)] px-2 text-nav font-medium text-sidebar-foreground transition-colors hover:bg-sidebar-accent/70 hover:text-sidebar-accent-foreground"
                            >
                                <Plus className="size-4 shrink-0" />
                                {t('chat.newSession')}
                            </Link>
                        </div>

                        <SidebarSessionList collapsed={false} />
                    </>
                )}

                <div className="shrink-0 border-t border-sidebar-border p-2">
                    <UserMenu />
                </div>
            </aside>
        </div>,
        document.body,
    )
}
