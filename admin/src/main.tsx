import { StrictMode } from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider, createRouter } from '@tanstack/react-router'
import { toast } from 'sonner'
import { setUnauthorizedHandler } from '@/core/http/client'
import { ApiError, getHttpErrorMessage } from '@/core/http/errors'
import { env } from '@/lib/env'
import { DirectionProvider } from './context/direction-provider'
import { FontProvider } from './context/font-provider'
import { ThemeProvider } from './context/theme-provider'
// Generated Routes
import { routeTree } from './routeTree.gen'
// Styles
import './styles/index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // 4xx 是确定性失败，重试无意义；其余最多重试 3 次
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
          return false
        }
        return failureCount < 3
      },
      refetchOnWindowFocus: false,
      staleTime: 10 * 1000,
    },
    mutations: {
      // 写操作的错误统一提示，业务组件只处理成功分支
      onError: (error) => {
        toast.error(getHttpErrorMessage(error))
      },
    },
  },
})

const router = createRouter({
  routeTree,
  // 生产部署在 /admin/ 下；本地开发为 undefined
  basepath: env.routerBasePath,
  context: { queryClient },
  defaultPreload: 'intent',
  defaultPreloadStaleTime: 0,
})

// 刷新令牌也失效时回到登录页，并保留回跳地址
setUnauthorizedHandler(() => {
  // latestLocation.href 已剥掉 basepath，可直接作为登录后的站内跳转目标
  const redirect = router.latestLocation.href
  void router.navigate({
    to: '/sign-in',
    search: { redirect },
    replace: true,
  })
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

const rootElement = document.getElementById('root')!
if (!rootElement.innerHTML) {
  const root = ReactDOM.createRoot(rootElement)
  root.render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <FontProvider>
            <DirectionProvider>
              <RouterProvider router={router} />
            </DirectionProvider>
          </FontProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </StrictMode>
  )
}
