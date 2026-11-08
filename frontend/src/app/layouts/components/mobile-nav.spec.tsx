import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactElement, ReactNode } from 'react'

import { useAppStore } from '@/app/stores/app-store'

// 抽屉只关心当前路径是否变化，测试里固定为新对话地址即可，避免引入真实路由实例
interface MockLinkProps {
    to: string
    children?: ReactNode
    className?: string
    activeOptions?: { exact?: boolean }
    activeProps?: { className?: string }
    'aria-label'?: string
}

vi.mock('@tanstack/react-router', async () => {
    const { createElement } = await import('react')

    return {
        // 只透传链接需要的属性，TanStack 的 activeOptions/activeProps 不属于 DOM 属性
        Link: ({ to, children, className, 'aria-label': ariaLabel }: MockLinkProps) =>
            createElement('a', { href: to, className, 'aria-label': ariaLabel }, children),
        useRouterState: (
            options: { select?: (state: { location: { pathname: string } }) => unknown } = {},
        ) => {
            const snapshot = { location: { pathname: '/chat/new' } }
            return options.select ? options.select(snapshot) : snapshot
        },
        useNavigate: () => async () => undefined,
        useParams: () => ({ section: 'general' }),
    }
})

// 会话列表依赖 Query 与路由上下文，抽屉用例只验证开合行为，这里替换为轻量占位
vi.mock('./sidebar-session-list', async () => {
    const { createElement } = await import('react')

    return {
        SidebarSessionList: () => createElement('div', { 'data-testid': 'sidebar-sessions' }),
    }
})

import { MobileNav } from './mobile-nav'

const openNav = (): void => {
    act(() => {
        useAppStore.getState().openMobileNav()
    })
}

// 账户菜单读取资料接口，需要 Query 上下文；未登录态不会真正发请求
const renderWithQuery = (ui: ReactElement): void => {
    render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>)
}

describe('MobileNav', () => {
    beforeEach(() => {
        window.localStorage.clear()
        // 抽屉状态是跨用例共享的单例，逐个复位避免上一个用例的展开态泄漏
        useAppStore.setState({ isMobileNavOpen: false })
    })

    it('打开后以对话框形式展示导航内容', () => {
        renderWithQuery(<MobileNav />)
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

        openNav()

        expect(screen.getByRole('dialog', { name: '主导航' })).toBeInTheDocument()
    })

    it('点击关闭按钮收起抽屉', () => {
        renderWithQuery(<MobileNav />)
        openNav()

        fireEvent.click(screen.getByRole('button', { name: '关闭导航' }))

        expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
        expect(useAppStore.getState().isMobileNavOpen).toBe(false)
    })

    it('按 Escape 收起抽屉，保证键盘用户可以退出遮挡', () => {
        renderWithQuery(<MobileNav />)
        openNav()

        fireEvent.keyDown(window, { key: 'Escape' })

        expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
        expect(useAppStore.getState().isMobileNavOpen).toBe(false)
    })
})
