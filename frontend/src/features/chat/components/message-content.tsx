import { useMemo, type ReactNode } from 'react'

import { OpenUiBlock, splitUiBlocks, useOpenUiEnabled } from '@/features/generative-ui'

import type { ChatMessageStatus } from '../runtime/types'
import { MarkdownContent } from './markdown-content'

export interface MessageContentProps {
  readonly content: string
  readonly status: ChatMessageStatus
  readonly threadId: string
  readonly onContinueConversation?: (message: string) => void
  readonly onOpenUrl?: (url: string) => void
  /** 消息含 buildResult 时由 MessageItem 注入，打开固定样式详情面板 */
  readonly onOpenBuildDetail?: () => void
  /** 本轮存在待澄清中断：屏蔽生成式 Form，只保留 HITL 表单入口 */
  readonly isHitlPending?: boolean
}

/**
 * 助手消息内容渲染。
 *
 * 开关关闭或文本中没有 openui 围栏时，仍走原来的 Markdown 路径（逐字节回退）；
 * 开关打开且存在 UI 块时按段渲染：Markdown 保持原样，已闭合 UI 块交给渲染器，
 * 流式中的尾块只显示占位，避免把半截 DSL 当成组件树执行。
 */
export function MessageContent({
  content,
  status,
  threadId,
  onContinueConversation,
  onOpenUrl,
  onOpenBuildDetail,
  isHitlPending = false,
}: MessageContentProps): ReactNode {
  const isOpenUiEnabled = useOpenUiEnabled()
  const splitResult = useMemo(
    () => (isOpenUiEnabled ? splitUiBlocks(content) : null),
    [content, isOpenUiEnabled],
  )

  const isStreaming = status === 'streaming'
  const isLive = status === 'pending' || isStreaming

  if (!splitResult || !splitResult.hasOpenUi) {
    return <MarkdownContent content={content} streaming={isStreaming} className="mt-1.5" />
  }

  const callbacks = {
    ...(onContinueConversation ? { onContinueConversation } : {}),
    ...(onOpenUrl ? { onOpenUrl } : {}),
    ...(onOpenBuildDetail ? { onOpenBuildDetail } : {}),
  }
  const lastIndex = splitResult.segments.length - 1

  return (
    <div className="mt-1.5 space-y-2">
      {splitResult.segments.map((segment, index) =>
        segment.kind === 'markdown' ? (
          <MarkdownContent
            key={segment.id}
            content={segment.content}
            streaming={isStreaming && index === lastIndex}
          />
        ) : (
          <OpenUiBlock
            key={segment.id}
            threadId={threadId}
            content={segment.content}
            isComplete={segment.isComplete}
            isMessageStreaming={isLive}
            {...(isHitlPending ? { disableForms: true } : {})}
            {...callbacks}
          />
        ),
      )}
    </div>
  )
}
