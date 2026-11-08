import { beforeEach, describe, expect, it } from 'vitest'

import { STORAGE_KEYS } from '@/constants/storage'
import {
  DEFAULT_SIDEBAR_WIDTH,
  readAppPreferences,
  writeAppPreferences,
} from '@/shared/lib/app-storage'

describe('app-storage', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('存储为空时返回默认偏好', () => {
    expect(readAppPreferences()).toEqual({
      theme: 'system',
      locale: 'zh-CN',
      isSidebarCollapsed: false,
      sidebarWidth: DEFAULT_SIDEBAR_WIDTH,
      showAccountMenuIcon: true,
      showTimestamps: false,
      fontScale: 'default',
    })
  })

  it('读取平铺结构中的合法字段', () => {
    window.localStorage.setItem(
      STORAGE_KEYS.appState,
      JSON.stringify({
        theme: 'dark',
        locale: 'en-US',
        isSidebarCollapsed: true,
        sidebarWidth: 320,
        showAccountMenuIcon: false,
      }),
    )

    expect(readAppPreferences()).toEqual({
      theme: 'dark',
      locale: 'en-US',
      isSidebarCollapsed: true,
      sidebarWidth: 320,
      showAccountMenuIcon: false,
      showTimestamps: false,
      fontScale: 'default',
    })
  })

  it('非法字段逐项回退默认值而不整体丢弃', () => {
    window.localStorage.setItem(
      STORAGE_KEYS.appState,
      JSON.stringify({ theme: 'blue', locale: 'en-US', sidebarWidth: -1 }),
    )

    expect(readAppPreferences()).toMatchObject({
      theme: 'system',
      locale: 'en-US',
      sidebarWidth: DEFAULT_SIDEBAR_WIDTH,
    })
  })

  it('内容损坏时回退默认偏好', () => {
    window.localStorage.setItem(STORAGE_KEYS.appState, '{not-json')

    expect(readAppPreferences().theme).toBe('system')
  })

  it('写入时保留 Vue 侧写入的未知字段，结构保持平铺', () => {
    window.localStorage.setItem(
      STORAGE_KEYS.appState,
      JSON.stringify({ theme: 'light', legacyFlag: 'keep-me' }),
    )

    writeAppPreferences({ theme: 'dark' })

    const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEYS.appState) ?? '{}')

    expect(stored).toEqual({ theme: 'dark', legacyFlag: 'keep-me' })
    // 禁止出现 { state, version } 包装，否则首屏脚本与 Vue 回滚会失效
    expect(stored).not.toHaveProperty('state')
    expect(stored).not.toHaveProperty('version')
  })
})
