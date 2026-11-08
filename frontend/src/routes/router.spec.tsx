import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { TooltipProvider } from '@/shared/ui/tooltip'

vi.mock('@/features/auth/model/auth-session', () => {
  const state = {
    status: 'unauthenticated',
    user: null,
    login: vi.fn(),
    logout: vi.fn(),
    clearSession: vi.fn(),
    restoreSession: vi.fn(async () => false),
    refreshSessionToken: vi.fn(async () => null),
  }

  // 组件按 hook 形式调用（传 selector），守卫按 getState 形式调用，两种入口都要支持
  const useAuthSessionStore = Object.assign(
    (selector?: (value: typeof state) => unknown) => (selector ? selector(state) : state),
    { getState: () => state },
  )

  return {
    useAuthSessionStore,
    ensureAuthSession: vi.fn(async () => false),
  }
})

vi.mock('@/features/auth/api/queries', () => ({
  currentUserQueryOptions: {
    queryKey: ['auth', 'current-user'],
    queryFn: async () => ({ publicId: 'u-1', username: 'tester', roles: [] }),
    staleTime: Number.POSITIVE_INFINITY,
  },
}))

import { createAppRouter } from './router'

function renderAt(path: string) {
  // 浏览器历史决定 RouterProvider 的初始匹配路径，先切换再渲染
  window.history.pushState({}, '', path)
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createAppRouter({ queryClient })
  render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <RouterProvider router={router} />
      </TooltipProvider>
    </QueryClientProvider>,
  )
  return router
}

describe('router', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('根路径展示欢迎页', async () => {
    renderAt('/')

    expect(await screen.findByRole('link', { name: '开始新对话' })).toBeInTheDocument()
  })

  it('旧欢迎地址重定向到根路径', async () => {
    const router = renderAt('/welcome')

    expect(await screen.findByRole('link', { name: '开始新对话' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/')
  })

  it('未登录访问受保护路由时跳转登录页并保留回跳地址', async () => {
    const router = renderAt('/chat/new')

    // 登录页是懒加载路由，并行跑全量用例时动态导入可能超过默认 1s 等待
    expect(
      await screen.findByRole('heading', { name: '登录' }, { timeout: 3000 }),
    ).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/login')
    expect(decodeURIComponent(router.state.location.searchStr)).toContain('redirect=/chat/new')
  })

  it('登录页渲染用户名与密码表单', async () => {
    renderAt('/login')

    expect(await screen.findByLabelText('用户名')).toBeInTheDocument()
    expect(screen.getByLabelText('密码')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '登录' })).toBeInTheDocument()
  })

  it('未知路径回退到 404 页面', async () => {
    renderAt('/not-exists')

    expect(await screen.findByRole('heading', { name: '页面不存在' })).toBeInTheDocument()
  })

  it('设计系统页可直接访问', async () => {
    renderAt('/design-system')

    expect(await screen.findByRole('heading', { name: '设计系统' })).toBeInTheDocument()
  })
})
