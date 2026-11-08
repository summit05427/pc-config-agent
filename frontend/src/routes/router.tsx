import type { QueryClient } from '@tanstack/react-query'
import {
  createRootRouteWithContext,
  createRoute,
  createRouter,
  lazyRouteComponent,
  notFound,
  redirect,
} from '@tanstack/react-router'

import { queryClient as defaultQueryClient } from '@/app/query-client'
import { RouteError } from '@/app/components/route-error'
import { BlankLayout } from '@/app/layouts/BlankLayout'
import { DefaultLayout } from '@/app/layouts/DefaultLayout'
import { useAuthSessionStore } from '@/features/auth/model/auth-session'
import {
  DEFAULT_SETTINGS_SECTION,
  isSettingsSectionId,
} from '@/features/settings/model/settings-sections'
import { env } from '@/shared/lib/env'

import { redirectAuthenticatedUser, requireAuthenticated, type RouterContext } from './guards'
import { NotFoundPage } from './pages/not-found-page'
import { ROUTE_PATHS } from './paths'

const WelcomePage = lazyRouteComponent(() => import('./pages/welcome-page'), 'WelcomePage')
const LoginPage = lazyRouteComponent(() => import('./pages/login-page'), 'LoginPage')
const SettingsPage = lazyRouteComponent(() => import('./pages/settings-page'), 'SettingsPage')
const ChatNewPage = lazyRouteComponent(() => import('./pages/chat-page'), 'ChatNewPage')
const ChatSessionPage = lazyRouteComponent(() => import('./pages/chat-page'), 'ChatSessionPage')
const ProtectedPlaceholderPage = lazyRouteComponent(
  () => import('./pages/protected-placeholder-page'),
  'ProtectedPlaceholderPage',
)
const DesignSystemPage = lazyRouteComponent(
  () => import('./design-system-page'),
  'DesignSystemPage',
)
const OpenUiDemoPage = lazyRouteComponent(
  () => import('./pages/openui-demo-page'),
  'OpenUiDemoPage',
)

interface LoginSearch {
  redirect?: string
}

/** 只接受字符串回跳参数，其余类型一律丢弃，避免把任意对象带进导航 */
const parseLoginSearch = (search: Record<string, unknown>): LoginSearch => ({
  redirect: typeof search.redirect === 'string' ? search.redirect : undefined,
})

export interface CreateAppRouterOptions {
  /** 允许单测注入独立缓存，生产默认使用应用单例 */
  queryClient?: QueryClient
}

/**
 * 创建路由实例。
 *
 * 抽成工厂函数是为了让单测拿到独立实例，避免多个用例共享匹配状态。
 * 守卫只做权限判断、重定向与 ensureQueryData 预热，具体页面仍在 lazyRouteComponent 中加载。
 */
export function createAppRouter(options: CreateAppRouterOptions = {}) {
  const appQueryClient = options.queryClient ?? defaultQueryClient

  const rootRoute = createRootRouteWithContext<RouterContext>()({
    // 公开路由（欢迎、登录、404、设计系统）共用无侧栏的全屏外壳
    component: BlankLayout,
    notFoundComponent: NotFoundPage,
  })

  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: ROUTE_PATHS.welcome,
    component: WelcomePage,
  })

  // 保留旧地址，避免已有收藏或外部链接失效
  const welcomeAliasRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: ROUTE_PATHS.welcomeAlias,
    beforeLoad: () => {
      throw redirect({ to: ROUTE_PATHS.welcome })
    },
  })

  const loginRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: ROUTE_PATHS.login,
    validateSearch: parseLoginSearch,
    beforeLoad: redirectAuthenticatedUser,
    component: LoginPage,
  })

  const designSystemRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: ROUTE_PATHS.designSystem,
    component: DesignSystemPage,
  })

  // 渲染演示只在开发环境可达；生产构建下访问直接落到 404，不暴露内部调试页
  const openUiDemoRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: ROUTE_PATHS.openUiDemo,
    beforeLoad: () => {
      if (env.appEnv !== 'development') {
        throw notFound()
      }
    },
    component: OpenUiDemoPage,
  })

  // 无路径布局路由：受保护页面共用认证守卫、用户预热与应用外壳
  const authenticatedRoute = createRoute({
    getParentRoute: () => rootRoute,
    id: '_authenticated',
    beforeLoad: requireAuthenticated,
    component: DefaultLayout,
    // 渲染期异常落在布局层，统一展示可重试的错误页而不是整页白屏
    errorComponent: RouteError,
  })

  // 静态路径必须声明在动态路径之前，避免 /chat/new 被当成 sessionId
  const chatNewRoute = createRoute({
    getParentRoute: () => authenticatedRoute,
    path: ROUTE_PATHS.chatNew,
    component: ChatNewPage,
  })

  const chatSessionRoute = createRoute({
    getParentRoute: () => authenticatedRoute,
    path: ROUTE_PATHS.chatSession,
    component: ChatSessionPage,
  })

  // 设置分类只认合法值：缺省与非法分类都重定向到规范地址，保证可刷新、可分享
  const settingsRoute = createRoute({
    getParentRoute: () => authenticatedRoute,
    path: ROUTE_PATHS.settings,
    beforeLoad: () => {
      throw redirect({
        to: ROUTE_PATHS.settingsSection,
        params: { section: DEFAULT_SETTINGS_SECTION },
        replace: true,
      })
    },
  })

  const settingsSectionRoute = createRoute({
    getParentRoute: () => authenticatedRoute,
    path: ROUTE_PATHS.settingsSection,
    beforeLoad: ({ params }) => {
      if (!isSettingsSectionId(params.section)) {
        throw redirect({
          to: ROUTE_PATHS.settingsSection,
          params: { section: DEFAULT_SETTINGS_SECTION },
          replace: true,
        })
      }
    },
    component: SettingsPage,
  })

  const forbiddenRoute = createRoute({
    getParentRoute: () => authenticatedRoute,
    path: ROUTE_PATHS.forbidden,
    component: () => <ProtectedPlaceholderPage titleKey="routes.forbidden" />,
  })

  const routeTree = rootRoute.addChildren([
    indexRoute,
    welcomeAliasRoute,
    loginRoute,
    designSystemRoute,
    openUiDemoRoute,
    authenticatedRoute.addChildren([
      chatNewRoute,
      chatSessionRoute,
      settingsRoute,
      settingsSectionRoute,
      forbiddenRoute,
    ]),
  ])

  const router = createRouter({
    routeTree,
    context: { queryClient: appQueryClient },
  })

  return router
}

export const router = createAppRouter()

/**
 * 请求层确认刷新失败后的全局收尾：清会话并跳登录页。
 *
 * 由 main.tsx 显式注入 core/http 的 auth 模块，避免 core 反向依赖路由。
 */
export const handleUnauthorizedNavigation = (): void => {
  useAuthSessionStore.getState().clearSession()

  const currentHref = router.state.location.href
  const redirectTarget = currentHref.startsWith(ROUTE_PATHS.login) ? undefined : currentHref
  void router.navigate({
    to: ROUTE_PATHS.login,
    search: redirectTarget ? { redirect: redirectTarget } : {},
    replace: true,
  })
}

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
