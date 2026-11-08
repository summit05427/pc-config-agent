import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import { useAppStore } from '@/app/stores/app-store'
import enUS from '@/locales/en-US'
import zhCN from '@/locales/zh-CN'
import { DEFAULT_LOCALE } from '@/shared/types/app'

let isInitialized = false

const applyLocale = (locale: string): void => {
  void i18n.changeLanguage(locale)
  document.documentElement.lang = locale
}

/**
 * 初始化 i18next 并让它跟随 app store 的语言。
 *
 * store 是语言的唯一状态源：启动时读取持久化偏好，切换时写回 `app-state`
 * 并同步 `document.documentElement.lang`。`initAsync: false` 保证首屏渲染前
 * 词条已经就绪，不会闪回默认语言。
 */
export const initI18n = (): typeof i18n => {
  if (isInitialized) {
    return i18n
  }
  isInitialized = true

  const initialLocale = useAppStore.getState().locale

  void i18n.use(initReactI18next).init({
    resources: {
      'zh-CN': { translation: zhCN },
      'en-US': { translation: enUS },
    },
    lng: initialLocale,
    fallbackLng: DEFAULT_LOCALE,
    supportedLngs: ['zh-CN', 'en-US'],
    // 词条沿用 Vue 基线的单花括号占位符（如 `{page}`），与 i18next 默认的 `{{page}}` 不同，
    // 这里显式改成单花括号，避免迁移后分页、额度等文案直接展示原始占位符
    interpolation: { escapeValue: false, prefix: '{', suffix: '}' },
    initAsync: false,
    returnNull: false,
  })

  applyLocale(initialLocale)

  useAppStore.subscribe((state, previousState) => {
    if (state.locale !== previousState.locale) {
      applyLocale(state.locale)
    }
  })

  return i18n
}

export default i18n
