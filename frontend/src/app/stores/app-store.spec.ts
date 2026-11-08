import { beforeEach, describe, expect, it } from 'vitest'

import { createAppStore, selectResolvedTheme } from '@/app/stores/app-store'
import { DEFAULT_SIDEBAR_WIDTH } from '@/shared/lib/app-storage'
import { STORAGE_KEYS } from '@/constants/storage'
import type { AppPreferences } from '@/shared/types/app'

const preferences: AppPreferences = {
  theme: 'dark',
  locale: 'zh-CN',
  isSidebarCollapsed: false,
  sidebarWidth: DEFAULT_SIDEBAR_WIDTH,
  showAccountMenuIcon: true,
  showTimestamps: false,
  fontScale: 'default',
}

describe('app-store', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('使用注入的初始偏好', () => {
    const store = createAppStore(preferences)

    expect(store.getState().theme).toBe('dark')
  })

  it('切换主题后写入平铺的 app-state', () => {
    const store = createAppStore(preferences)
    store.getState().setTheme('light')

    const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEYS.appState) ?? '{}')

    expect(stored).toMatchObject({ theme: 'light', locale: 'zh-CN' })
    expect(stored).not.toHaveProperty('state')
  })

  it('toggleTheme 在暗色时切回浅色', () => {
    const store = createAppStore(preferences)
    store.getState().toggleTheme()

    expect(store.getState().theme).toBe('light')
  })

  it('system 模式下按系统偏好解析明暗', () => {
    const store = createAppStore({ ...preferences, theme: 'system' })
    store.getState().setSystemDark(true)
    expect(selectResolvedTheme(store.getState())).toBe('dark')

    store.getState().setSystemDark(false)
    expect(selectResolvedTheme(store.getState())).toBe('light')
  })

  it('侧栏折叠状态独立于宽度并持久化', () => {
    const store = createAppStore(preferences)
    store.getState().setSidebarCollapsed(true)
    store.getState().setSidebarWidth(320)

    const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEYS.appState) ?? '{}')

    expect(stored).toMatchObject({ isSidebarCollapsed: true, sidebarWidth: 320 })
  })

  it('账户菜单图标开关持久化到 app-state', () => {
    const store = createAppStore(preferences)
    store.getState().setShowAccountMenuIcon(false)

    const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEYS.appState) ?? '{}')

    expect(store.getState().showAccountMenuIcon).toBe(false)
    expect(stored).toMatchObject({ showAccountMenuIcon: false })
  })

  it('移动端抽屉只改内存态，不写入 app-state', () => {
    const store = createAppStore(preferences)
    // 先写入一次基线，确保检查的是「抽屉开关是否被追加进存储」而不是文件为空
    store.getState().setTheme('light')

    store.getState().openMobileNav()
    expect(store.getState().isMobileNavOpen).toBe(true)

    const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEYS.appState) ?? '{}')
    expect(stored).not.toHaveProperty('isMobileNavOpen')

    store.getState().closeMobileNav()
    expect(store.getState().isMobileNavOpen).toBe(false)
  })
})
