import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

import { initI18n } from '@/i18n'

// 单测中的页面同样依赖 useTranslation，测试环境启动时统一初始化
initI18n()

// 每个用例结束后卸载 React 树，避免上一用例的 DOM 与副作用残留到下一用例
afterEach(() => {
  cleanup()
})
