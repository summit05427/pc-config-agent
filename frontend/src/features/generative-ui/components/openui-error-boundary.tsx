import { Component, type ErrorInfo, type ReactNode } from 'react'

import { env } from '@/shared/lib/env'

export interface OpenUiErrorBoundaryProps {
  readonly children: ReactNode
  readonly fallback: ReactNode
}

interface OpenUiErrorBoundaryState {
  readonly hasError: boolean
}

/**
 * 生成式 UI 的单块隔离边界。
 *
 * React 19 仍未提供函数式错误边界，类组件是官方唯一形式；这是全仓唯一保留的
 * 类组件，只负责捕获插件渲染异常，业务 UI 仍全部使用函数组件。
 */
export class OpenUiErrorBoundary extends Component<
  OpenUiErrorBoundaryProps,
  OpenUiErrorBoundaryState
> {
  state: OpenUiErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError(): OpenUiErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // 只在本机开发时输出线索；生产环境不把堆栈暴露给用户或日志系统
    if (env.appEnv === 'development') {
      console.error('[openui] 渲染失败', error, info.componentStack)
    }
  }

  render(): ReactNode {
    return this.state.hasError ? this.props.fallback : this.props.children
  }
}
