import { STORAGE_KEYS } from '@/constants/storage'
import { createBrowserStore } from '@/shared/lib/browser-store'
import {
  DEFAULT_FONT_SCALE,
  DEFAULT_LOCALE,
  DEFAULT_THEME,
  FONT_SCALES,
  SUPPORTED_LOCALES,
  THEME_MODES,
  type AppLocale,
  type AppPreferences,
  type FontScale,
  type ThemeMode,
} from '@/shared/types/app'

/** 侧栏展开宽度，沿用 CDS 的 288px；折叠态由 isSidebarCollapsed 单独表达 */
export const DEFAULT_SIDEBAR_WIDTH = 288

/** 界面偏好跨刷新保留，固定走 localStorage；键名与结构与 index.html 首屏脚本共用 */
const appStateStore = createBrowserStore({ area: 'local' })

const isPlainRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const hasValue = (values: readonly string[], value: unknown): boolean =>
  typeof value === 'string' && values.includes(value)

const isThemeMode = (value: unknown): value is ThemeMode => hasValue(THEME_MODES, value)

const isAppLocale = (value: unknown): value is AppLocale => hasValue(SUPPORTED_LOCALES, value)

const isFontScale = (value: unknown): value is FontScale => hasValue(FONT_SCALES, value)

const isSidebarWidth = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value > 0

/**
 * 读取 `app-state` 中的界面偏好。
 * 结构是平铺的 `{ theme, locale, isSidebarCollapsed, sidebarWidth }`，不使用
 * Zustand persist 的 `{ state, version }` 包装，否则 `index.html` 首屏脚本与
 * Vue 回滚都会失效。解析失败或字段非法时逐字段回退默认值，不抛异常。
 */
export function readAppPreferences(): AppPreferences {
  const defaults: AppPreferences = {
    theme: DEFAULT_THEME,
    locale: DEFAULT_LOCALE,
    isSidebarCollapsed: false,
    sidebarWidth: DEFAULT_SIDEBAR_WIDTH,
    showAccountMenuIcon: true,
    showTimestamps: false,
    fontScale: DEFAULT_FONT_SCALE,
  }

  const stored = appStateStore.readJson<unknown>(STORAGE_KEYS.appState)
  if (!isPlainRecord(stored)) {
    return defaults
  }

  return {
    theme: isThemeMode(stored.theme) ? stored.theme : defaults.theme,
    locale: isAppLocale(stored.locale) ? stored.locale : defaults.locale,
    isSidebarCollapsed:
      typeof stored.isSidebarCollapsed === 'boolean'
        ? stored.isSidebarCollapsed
        : defaults.isSidebarCollapsed,
    sidebarWidth: isSidebarWidth(stored.sidebarWidth) ? stored.sidebarWidth : defaults.sidebarWidth,
    showAccountMenuIcon:
      typeof stored.showAccountMenuIcon === 'boolean'
        ? stored.showAccountMenuIcon
        : defaults.showAccountMenuIcon,
    showTimestamps:
      typeof stored.showTimestamps === 'boolean'
        ? stored.showTimestamps
        : defaults.showTimestamps,
    fontScale: isFontScale(stored.fontScale) ? stored.fontScale : defaults.fontScale,
  }
}

/**
 * 写入界面偏好。
 * 读取原对象后做浅合并，保留 Vue 侧写入的其他字段，避免迁移期互相覆盖。
 */
export function writeAppPreferences(preferences: Partial<AppPreferences>): void {
  const current = appStateStore.readJson<unknown>(STORAGE_KEYS.appState)

  // 旧值损坏时从空对象重建，避免一条坏数据永久阻塞偏好写入
  appStateStore.writeJson(STORAGE_KEYS.appState, {
    ...(isPlainRecord(current) ? current : {}),
    ...preferences,
  })
}
