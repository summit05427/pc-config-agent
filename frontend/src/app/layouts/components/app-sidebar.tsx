import { useLayoutEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from '@tanstack/react-router'
import { PanelLeftClose, PanelLeftOpen, Plus } from 'lucide-react'

import { useAppStore } from '@/app/stores/app-store'
import { SettingsNav } from '@/features/settings/components/settings-nav'
import { resolveSettingsSection } from '@/features/settings/model/settings-sections'
import { ROUTE_PATHS } from '@/routes/paths'
import { BrandMark } from '@/shared/ui/brand-mark'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/utils'

import { useViewportWidth } from '../hooks/use-viewport-width'
import type { SidebarMode } from '../lib/nav'
import { clampExpandedWidth, resolveSidebarCommit, resolveSidebarMaxWidth } from '../lib/sidebar'
import { AppLogo } from './app-logo'
import { SidebarResizer } from './sidebar-resizer'
import { SidebarSessionList } from './sidebar-session-list'
import { UserMenu } from './user-menu'

export interface AppSidebarProps {
    /** 设置模式下导航与会话列表整体替换为设置目录 */
    mode?: SidebarMode
}

/**
 * 桌面侧边栏。
 *
 * 折叠态与宽度来自 app-store（落盘四字段），拖拽只改 DOM 宽度，提交时才写 store；
 * 视口上限优先于用户偏好，窗口变窄时实际宽度跟着收缩但不覆盖偏好值。
 */
export function AppSidebar({ mode = 'default' }: AppSidebarProps) {
    const { t } = useTranslation()
    const params = useParams({ strict: false })
    const activeSection = resolveSettingsSection(params.section)
    const isSettingsMode = mode === 'settings'
    const isCollapsed = useAppStore((state) => state.isSidebarCollapsed)
    const storedWidth = useAppStore((state) => state.sidebarWidth)
    const setSidebarCollapsed = useAppStore((state) => state.setSidebarCollapsed)
    const setSidebarWidth = useAppStore((state) => state.setSidebarWidth)
    const viewportWidth = useViewportWidth()
    const asideRef = useRef<HTMLElement | null>(null)
    const [isResizing, setIsResizing] = useState(false)

    const maximumWidth = resolveSidebarMaxWidth(viewportWidth)
    const sidebarWidth = clampExpandedWidth(storedWidth, maximumWidth)

    // 展开宽度必须由 DOM 写入：JSX 行内 style 在规范里被禁止，且拖动期间需要绕过重渲染。
    // 用 layout effect 在浏览器绘制前同步宽度，折叠/展开才能从当前计算宽度平滑过渡。
    useLayoutEffect(() => {
        const element = asideRef.current
        if (!element) {
            return
        }
        if (isCollapsed) {
            // 折叠宽度交给 rail 类；移除行内值后 width 从展开值过渡到 rail 宽度
            element.style.removeProperty('width')
            return
        }
        element.style.width = `${sidebarWidth}px`
    }, [isCollapsed, sidebarWidth])

    const focusExpandControl = (): void => {
        // 等折叠状态渲染完成再聚焦，避免焦点落回 body
        window.requestAnimationFrame(() => {
            document.querySelector<HTMLElement>('[data-sidebar-expand]')?.focus()
        })
    }

    const collapseSidebar = (): void => {
        setSidebarCollapsed(true)
        focusExpandControl()
    }

    const handleResizeCommit = (width: number): void => {
        setIsResizing(false)
        const next = resolveSidebarCommit(width, maximumWidth)

        if (next.collapsed) {
            setSidebarCollapsed(true)
            focusExpandControl()
            return
        }

        setSidebarCollapsed(false)
        setSidebarWidth(next.width)
        // 默认宽度与阈值之间需要吸附，先写回最终值，避免等到下一帧才更新
        if (asideRef.current) {
            asideRef.current.style.width = `${next.width}px`
        }
    }

    return (
        <aside
            ref={asideRef}
            className={cn(
                'relative hidden shrink-0 flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-200 ease-out motion-reduce:transition-none md:flex',
                isCollapsed && 'w-[var(--app-sidebar-rail-width)]',
                // 拖动期间关闭过渡，保证宽度跟手；结束后恢复动画
                isResizing && 'transition-none',
            )}
        >
            <div
                className={cn(
                    'flex h-[var(--app-titlebar-height)] shrink-0 items-center px-3',
                    isCollapsed ? 'justify-center' : 'justify-between gap-2',
                )}
            >
                {isCollapsed ? (
                    // 折叠态不展示品牌链接，悬浮时整块变为展开按钮，避免出现第二个底部入口
                    <Button
                        variant="ghost"
                        size="icon-sm"
                        data-sidebar-expand
                        title={t('layout.expandSidebar')}
                        aria-label={t('layout.expandSidebar')}
                        className="group/logo relative"
                        onClick={() => setSidebarCollapsed(false)}
                    >
                        <span className="flex transition-opacity group-hover/logo:opacity-0 group-focus-visible/logo:opacity-0">
                            <BrandMark size="sm" />
                        </span>
                        <PanelLeftOpen className="absolute inset-0 m-auto size-4 opacity-0 transition-opacity group-hover/logo:opacity-100 group-focus-visible/logo:opacity-100" />
                    </Button>
                ) : (
                    <AppLogo />
                )}

                {isCollapsed ? null : (
                    <Button variant="ghost" size="icon-sm" aria-label={t('layout.collapseSidebar')} onClick={collapseSidebar}>
                        <PanelLeftClose className="size-4" />
                    </Button>
                )}
            </div>

            {isSettingsMode ? null : (
                <div className={cn('px-2 pb-1', isCollapsed && 'flex justify-center')}>
                    <Link
                        to={ROUTE_PATHS.chatNew}
                        title={isCollapsed ? t('chat.newSession') : undefined}
                        className={cn(
                            'flex h-[var(--app-sidebar-row-height)] items-center gap-2 rounded-[var(--cds-radius-btn-xs)] px-2 text-nav font-medium text-sidebar-foreground transition-colors hover:bg-sidebar-accent/70 hover:text-sidebar-accent-foreground',
                            isCollapsed ? 'w-[var(--app-sidebar-row-height)] justify-center px-0' : 'w-full',
                        )}
                    >
                        <Plus className="size-4 shrink-0" />
                        {isCollapsed ? (
                            <span className="sr-only">{t('chat.newSession')}</span>
                        ) : (
                            <span className="min-w-0 truncate">{t('chat.newSession')}</span>
                        )}
                    </Link>
                </div>
            )}

            {isSettingsMode ? (
                <SettingsNav activeSection={activeSection} collapsed={isCollapsed} />
            ) : (
                <SidebarSessionList collapsed={isCollapsed} />
            )}

            <div className="shrink-0 border-t border-sidebar-border p-2">
                {isCollapsed ? (
                    <div className="flex justify-center">
                        <UserMenu compact />
                    </div>
                ) : (
                    <UserMenu />
                )}
            </div>

            <SidebarResizer
                width={sidebarWidth}
                max={maximumWidth}
                collapsed={isCollapsed}
                label={t('layout.resizeSidebar')}
                expandLabel={t('layout.expandSidebar')}
                onStart={() => setIsResizing(true)}
                onResize={(width) => {
                    if (asideRef.current) {
                        asideRef.current.style.width = `${width}px`
                    }
                }}
                onCommit={handleResizeCommit}
                onCancel={() => {
                    setIsResizing(false)
                    if (asideRef.current) {
                        asideRef.current.style.width = `${sidebarWidth}px`
                    }
                }}
                onExpand={() => setSidebarCollapsed(false)}
            />
        </aside>
    )
}
