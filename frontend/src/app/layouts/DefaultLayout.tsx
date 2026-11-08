import { Outlet, useRouterState } from '@tanstack/react-router'

import { ROUTE_PATHS } from '@/routes/paths'

import { AppSidebar } from './components/app-sidebar'
import { MobileNav } from './components/mobile-nav'
import { MobileNavTrigger } from './components/mobile-nav-trigger'
import type { SidebarMode } from './lib/nav'

/**
 * 受保护页面外壳：左侧导航 + 窄屏抽屉入口 + 内容区。
 *
 * 内容区只提供高度，滚动交给页面自己管理，对话页才能固定输入区。
 * 设置路由下侧栏与抽屉切换为设置目录，右侧只保留内容列。
 */
export function DefaultLayout() {
    const pathname = useRouterState({ select: (state) => state.location.pathname })
    const isSettingsRoute =
        pathname === ROUTE_PATHS.settings || pathname.startsWith(`${ROUTE_PATHS.settings}/`)
    const sidebarMode: SidebarMode = isSettingsRoute ? 'settings' : 'default'

    return (
        <div className="flex h-dvh overflow-hidden bg-canvas text-foreground">
            <AppSidebar mode={sidebarMode} />
            <MobileNav mode={sidebarMode} />
            <MobileNavTrigger />

            <div className="flex min-w-0 flex-1 flex-col bg-background">
                <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
                    <Outlet />
                </main>
            </div>
        </div>
    )
}
