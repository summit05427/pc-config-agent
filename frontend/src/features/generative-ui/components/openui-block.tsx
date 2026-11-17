import { memo, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useOpenUiState } from '../hooks/use-openui-state'
import { FormDisabledContext } from '../library/components/form'
import { OpenUiRenderer } from './openui-renderer'

type RawFallbackMessageKey = 'generativeUi.incomplete' | 'generativeUi.renderFailed'

export interface OpenUiBlockProps {
  readonly threadId: string
  readonly content: string
  readonly isComplete: boolean
  /** 整条消息仍在流式输出；已闭合块也要禁用交互，避免和新轮次抢发送 */
  readonly isMessageStreaming: boolean
  /** 存在待澄清中断时为 true：隐藏生成式 Form，避免与 HITL 表单形成双入口 */
  readonly disableForms?: boolean
  readonly onContinueConversation?: (message: string) => void
  readonly onOpenUrl?: (url: string) => void
  /** 打开配置详情面板；仅在含 buildResult 的消息里由宿主传入 */
  readonly onOpenBuildDetail?: () => void
}

interface OpenUiRawFallbackProps {
  readonly content: string
  readonly messageKey: RawFallbackMessageKey
}

/** 渲染失败或围栏未闭合时的降级：保留原文，用户仍可复制或让模型重新生成 */
function OpenUiRawFallback({ content, messageKey }: OpenUiRawFallbackProps): ReactNode {
  const { t } = useTranslation()

  return (
    <div className="rounded-lg border border-border bg-muted/30 px-3 py-2">
      <p className="text-xs text-muted-foreground">{t(messageKey)}</p>
      <pre className="mt-1.5 overflow-x-auto whitespace-pre-wrap break-words font-mono text-xs text-foreground">
        {content}
      </pre>
    </div>
  )
}

/** 流式期间尾块尚未闭合：只给进度占位，不渲染半截 DSL */
function OpenUiStreamingPlaceholder(): ReactNode {
  const { t } = useTranslation()

  return (
    <div role="status" className="rounded-lg border border-dashed border-border bg-muted/30 px-3 py-3">
      <p className="text-xs text-muted-foreground">{t('generativeUi.streaming')}</p>
      <div className="mt-2 space-y-1.5" aria-hidden="true">
        <div className="skeleton h-2.5 w-2/3" />
        <div className="skeleton h-2.5 w-full" />
        <div className="skeleton h-2.5 w-1/2" />
      </div>
    </div>
  )
}

function OpenUiCompleteBlock({
  threadId,
  content,
  isMessageStreaming,
  disableForms = false,
  onContinueConversation,
  onOpenUrl,
  onOpenBuildDetail,
}: Omit<OpenUiBlockProps, 'isComplete'>): ReactNode {
  const { initialState, handleStateUpdate } = useOpenUiState(threadId, content)

  return (
    <FormDisabledContext.Provider value={disableForms}>
      <OpenUiRenderer
        response={content}
        isStreaming={isMessageStreaming}
        onStateUpdate={handleStateUpdate}
        {...(initialState ? { initialState } : {})}
        {...(onContinueConversation ? { onContinueConversation } : {})}
        {...(onOpenUrl ? { onOpenUrl } : {})}
        {...(onOpenBuildDetail ? { onOpenBuildDetail } : {})}
        fallback={<OpenUiRawFallback content={content} messageKey="generativeUi.renderFailed" />}
      />
    </FormDisabledContext.Provider>
  )
}

/**
 * 单个 OpenUI 块的展示状态机。
 *
 * 已闭合块交给真实渲染器；流式中的未闭合块只显示占位；终态仍未闭合则降级为原文。
 * 组件用 memo 固定已闭合块：后续 token 只改变尾块内容，不会让前面的重组件重复渲染。
 */
function OpenUiBlockComponent({
  threadId,
  content,
  isComplete,
  isMessageStreaming,
  disableForms,
  onContinueConversation,
  onOpenUrl,
  onOpenBuildDetail,
}: OpenUiBlockProps): ReactNode {
  if (!isComplete) {
    return isMessageStreaming ? (
      <OpenUiStreamingPlaceholder />
    ) : (
      <OpenUiRawFallback content={content} messageKey="generativeUi.incomplete" />
    )
  }

  return (
    <OpenUiCompleteBlock
      threadId={threadId}
      content={content}
      isMessageStreaming={isMessageStreaming}
      {...(disableForms ? { disableForms } : {})}
      {...(onContinueConversation ? { onContinueConversation } : {})}
      {...(onOpenUrl ? { onOpenUrl } : {})}
      {...(onOpenBuildDetail ? { onOpenBuildDetail } : {})}
    />
  )
}

export const OpenUiBlock = memo(OpenUiBlockComponent)
