import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'

import { queryClient } from '@/app/query-client'
import { AppToaster } from '@/app/providers/app-toaster'
import { ThemeProvider } from '@/app/providers/theme-provider'
import { installGlobalErrorHandlers } from '@/app/lib/report-error'
import { router } from '@/routes/router'
import { TooltipProvider } from '@/shared/ui/tooltip'

// 模块初始化时注册一次全局异常兜底；内部标记保证 HMR 重复执行时不会叠加监听
installGlobalErrorHandlers()

export function App() {
  return (
    <ThemeProvider>
      <TooltipProvider>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
          <AppToaster />
        </QueryClientProvider>
      </TooltipProvider>
    </ThemeProvider>
  )
}
