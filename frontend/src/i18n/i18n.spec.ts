import { afterEach, describe, expect, it } from 'vitest'

import { useAppStore } from '@/app/stores/app-store'
import enUS from '@/locales/en-US'
import zhCN from '@/locales/zh-CN'

import i18n, { initI18n } from './index'

const flattenKeys = (value: unknown, prefix = ''): string[] => {
  if (typeof value !== 'object' || value === null) {
    return [prefix]
  }

  return Object.entries(value).flatMap(([key, child]) =>
    flattenKeys(child, prefix ? `${prefix}.${key}` : key),
  )
}

describe('i18n', () => {
  afterEach(() => {
    useAppStore.getState().setLocale('zh-CN')
  })

  it('zh-CN 与 en-US 的 key 集合完全一致', () => {
    const zhKeys = flattenKeys(zhCN).sort()
    const enKeys = flattenKeys(enUS).sort()

    expect(enKeys).toEqual(zhKeys)
  })

  it('初始化后默认使用 app store 中的语言并同步 document.lang', () => {
    initI18n()

    expect(i18n.language).toBe('zh-CN')
    expect(document.documentElement.lang).toBe('zh-CN')
    expect(i18n.t('welcome.title')).toBe(zhCN.welcome.title)
  })

  it('切换 app store 语言时同步 i18next 与 document.lang', () => {
    initI18n()
    useAppStore.getState().setLocale('en-US')

    expect(i18n.language).toBe('en-US')
    expect(document.documentElement.lang).toBe('en-US')
    expect(i18n.t('welcome.title')).toBe(enUS.welcome.title)
  })

  it('重复初始化不会重复注册语言监听', () => {
    initI18n()
    initI18n()

    useAppStore.getState().setLocale('en-US')

    expect(i18n.language).toBe('en-US')
  })
})
