import { Outlet } from '@tanstack/react-router'

/**
 * 公开页面外壳：登录页与错误页各自负责版式，这里只提供全屏画布。
 * 受保护路由由 DefaultLayout 承担，两者不嵌套，避免把侧栏带到登录页。
 */
export function BlankLayout() {
    return (
        <div className="min-h-dvh bg-background text-foreground">
            <Outlet />
        </div>
    )
}
