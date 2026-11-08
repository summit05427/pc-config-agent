/**
 * 界面偏好与主题相关的公共类型。
 * 这些字段同时是 `localStorage['app-state']` 的持久化结构，改名或改类型会
 * 同时破坏首屏主题脚本与 Vue 回滚兼容，必须与 Vue 基线逐字段一致。
 */

export const THEME_MODES = ['light', 'dark', 'system'] as const

export type ThemeMode = (typeof THEME_MODES)[number]

export type ResolvedTheme = Exclude<ThemeMode, 'system'>

export const DEFAULT_THEME: ThemeMode = 'system'

export const SUPPORTED_LOCALES = ['zh-CN', 'en-US'] as const

export type AppLocale = (typeof SUPPORTED_LOCALES)[number]

export const DEFAULT_LOCALE: AppLocale = 'zh-CN'

/** 字号档位：根字号分别对应 15px / 16px / 17px */
export const FONT_SCALES = ['small', 'default', 'large'] as const

export type FontScale = (typeof FONT_SCALES)[number]

export const DEFAULT_FONT_SCALE: FontScale = 'default'

/**
 * 需要跨刷新保留的界面偏好，与 Vue 基线 `app-state` 的字段完全对应。
 * 旧版本或 Vue 侧忽略未知键即可；首屏脚本只读取 `theme` 与 `fontScale`，
 * 其余字段不影响首屏渲染。
 */
export interface AppPreferences {
  theme: ThemeMode
  locale: AppLocale
  isSidebarCollapsed: boolean
  sidebarWidth: number
  /** 侧边栏底部账户入口右侧的菜单图标；关闭只隐藏图标，入口本身仍可点击 */
  showAccountMenuIcon: boolean
  /** Agent 回复末尾显示时间戳 */
  showTimestamps: boolean
  /** 全局字号档位 */
  fontScale: FontScale
}
