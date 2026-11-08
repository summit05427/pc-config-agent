import { create, type StoreApi, type UseBoundStore } from 'zustand'
import { immer } from 'zustand/middleware/immer'

import { readAppPreferences, writeAppPreferences } from '@/shared/lib/app-storage'
import type {
  AppLocale,
  AppPreferences,
  FontScale,
  ResolvedTheme,
  ThemeMode,
} from '@/shared/types/app'

export interface AppStore extends AppPreferences {
  /** 系统是否处于暗色偏好；仅 system 模式使用，由 ThemeProvider 监听后写入 */
  isSystemDark: boolean
  /**
   * 窄屏导航抽屉是否展开。
   * 纯内存态：刷新后应回到收起状态，因此不进入 `app-state` 的持久化字段。
   */
  isMobileNavOpen: boolean
  setTheme(mode: ThemeMode): void
  toggleTheme(): void
  setLocale(locale: AppLocale): void
  setSidebarCollapsed(collapsed: boolean): void
  setSidebarWidth(width: number): void
  setShowAccountMenuIcon(visible: boolean): void
  setShowTimestamps(visible: boolean): void
  setFontScale(scale: FontScale): void
  setSystemDark(isDark: boolean): void
  openMobileNav(): void
  closeMobileNav(): void
}

/** 把主题模式解析成实际明暗结果，与 index.html 首屏脚本的判定顺序一致 */
export function selectResolvedTheme(state: AppStore): ResolvedTheme {
  if (state.theme === 'system') {
    return state.isSystemDark ? 'dark' : 'light'
  }

  return state.theme
}

/**
 * 创建应用级 UI store。
 * 抽成工厂函数便于单测注入初始偏好；生产环境使用下方单例。
 * 持久化不依赖 Zustand 的 persist 中间件，避免引入 `{ state, version }` 包装。
 */
export function createAppStore(
  initialPreferences: AppPreferences = readAppPreferences(),
): UseBoundStore<StoreApi<AppStore>> {
  return create<AppStore>()(
    // immer 中间件让 set 支持 mutate 写法：直接改 draft 即可生成不可变新快照
    immer((set, get) => {
      // 每次变更都写入完整的偏好字段，与 Vue 基线持久化插件的行为一致，
      // 保证回滚时读到的 app-state 结构完整而非只剩被改过的键
      const commit = (patch: Partial<AppPreferences>): void => {
        set(patch)

        const state = get()
        writeAppPreferences({
          theme: state.theme,
          locale: state.locale,
          isSidebarCollapsed: state.isSidebarCollapsed,
          sidebarWidth: state.sidebarWidth,
          showAccountMenuIcon: state.showAccountMenuIcon,
          showTimestamps: state.showTimestamps,
          fontScale: state.fontScale,
        })
      }

      return {
        ...initialPreferences,
        isSystemDark: false,
        isMobileNavOpen: false,
        setTheme: (theme) => commit({ theme }),
        toggleTheme: () =>
          commit({ theme: selectResolvedTheme(get()) === 'dark' ? 'light' : 'dark' }),
        setLocale: (locale) => commit({ locale }),
        setSidebarCollapsed: (isSidebarCollapsed) => commit({ isSidebarCollapsed }),
        setSidebarWidth: (sidebarWidth) => commit({ sidebarWidth }),
        setShowAccountMenuIcon: (showAccountMenuIcon) => commit({ showAccountMenuIcon }),
        setShowTimestamps: (showTimestamps) => commit({ showTimestamps }),
        setFontScale: (fontScale) => commit({ fontScale }),
        setSystemDark: (isSystemDark) => set({ isSystemDark }),
        // 抽屉开合只影响当前会话的界面，不写入 localStorage
        openMobileNav: () => set({ isMobileNavOpen: true }),
        closeMobileNav: () => set({ isMobileNavOpen: false }),
      }
    }),
  )
}

export const useAppStore = createAppStore()
