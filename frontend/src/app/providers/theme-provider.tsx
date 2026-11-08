import { useEffect, type ReactNode } from 'react'

import { selectResolvedTheme, useAppStore } from '@/app/stores/app-store'

const DARK_SCHEME_QUERY = '(prefers-color-scheme: dark)'

/**
 * 主题 Provider：
 * 1. 监听系统明暗偏好并写回 store，使 system 模式实时生效；
 * 2. 把解析后的明暗结果同步到 `documentElement` 的 `.dark` 类，
 *    与 index.html 首屏脚本使用同一个类，切换时不产生第二套判定；
 * 3. 把字号档位同步到 `data-font-scale`，由 CSS 根字号统一缩放。
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const resolvedTheme = useAppStore(selectResolvedTheme)
  const fontScale = useAppStore((state) => state.fontScale)
  const setSystemDark = useAppStore((state) => state.setSystemDark)

  useEffect(() => {
    const mediaQuery = window.matchMedia(DARK_SCHEME_QUERY)
    setSystemDark(mediaQuery.matches)

    const handleChange = (event: MediaQueryListEvent): void => setSystemDark(event.matches)
    mediaQuery.addEventListener('change', handleChange)

    return () => mediaQuery.removeEventListener('change', handleChange)
  }, [setSystemDark])

  useEffect(() => {
    document.documentElement.classList.toggle('dark', resolvedTheme === 'dark')
  }, [resolvedTheme])

  useEffect(() => {
    document.documentElement.dataset.fontScale = fontScale
  }, [fontScale])

  return <>{children}</>
}
