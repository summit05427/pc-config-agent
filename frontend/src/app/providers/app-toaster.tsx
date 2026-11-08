import { Toaster } from 'sonner'

import { selectResolvedTheme, useAppStore } from '@/app/stores/app-store'

/** Toast 宿主：主题跟随应用 store，不使用 next-themes，避免把 Next.js 依赖带进 Vite 工程 */
export function AppToaster() {
  const theme = useAppStore(selectResolvedTheme)

  return <Toaster theme={theme} position="top-center" richColors closeButton />
}
