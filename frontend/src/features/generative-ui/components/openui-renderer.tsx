import { lazy, Suspense, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useOpenUiEnabled } from '../hooks/use-openui'
import type { OpenUiRendererProps } from '../types'
import { OpenUiErrorBoundary } from './openui-error-boundary'

const OpenUiRendererRuntime = lazy(async () => {
  const module = await import('./openui-renderer-runtime')
  return { default: module.OpenUiRendererRuntime }
})

export interface OpenUiRendererWrapperProps extends OpenUiRendererProps {
  /** 单块异常时的降级内容；调用方可传入保留原文的代码块 */
  readonly fallback?: ReactNode
}

interface OpenUiFallbackProps {
  readonly isLoading?: boolean
}

function OpenUiFallback({ isLoading = false }: OpenUiFallbackProps): ReactNode {
  const { t } = useTranslation()

  return (
    <div
      role="status"
      className="rounded-lg border border-dashed border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground"
    >
      {isLoading ? t('generativeUi.loading') : t('generativeUi.renderFailed')}
    </div>
  )
}

/**
 * 生成式 UI 的安全入口。
 *
 * 关闭开关时返回 null，调用方应回退到原始 Markdown；渲染异常被单块边界隔离，
 * 不会影响同一消息中的其他段落与整个聊天工作区。
 */
export function OpenUiRenderer({ fallback, ...props }: OpenUiRendererWrapperProps): ReactNode {
  const isOpenUiEnabled = useOpenUiEnabled()

  if (!isOpenUiEnabled) {
    return null
  }

  return (
    // key 随内容变化重建边界：一次渲染异常不会让后续流式内容永久降级
    <OpenUiErrorBoundary key={props.response} fallback={fallback ?? <OpenUiFallback />}>
      <Suspense fallback={<OpenUiFallback isLoading />}>
        <OpenUiRendererRuntime {...props} />
      </Suspense>
    </OpenUiErrorBoundary>
  )
}
