import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from '@/app/app'
import { configureAuth } from '@/core/http'
import { useAuthSessionStore } from '@/features/auth/model/auth-session'
import { handleUnauthorizedNavigation } from '@/routes/router'
import { initI18n } from '@/i18n'

import './styles/main.css'

const container = document.getElementById('app')

if (!container) {
  throw new Error('缺少挂载节点 #app')
}

// 刷新实现与全局跳转在这里显式装配：core/http 不反向依赖认证模块与路由
configureAuth({
  refresh: () => useAuthSessionStore.getState().refreshSessionToken(),
  onUnauthorized: handleUnauthorizedNavigation,
})

// 语言必须在首次渲染前就绪，否则首屏会先渲染默认语言再切换
initI18n()

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
