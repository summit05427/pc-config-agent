import { useCallback, useLayoutEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowDown } from 'lucide-react'

import type { HitlInterrupt } from '@/features/sessions/api'
import { Button } from '@/shared/ui/button'

import type { RuntimeMessage } from '../runtime/types'
import { ChatEmptyState } from './chat-empty-state'
import { MessageItem } from './message-item'

const PIN_THRESHOLD = 96
const SKELETON_ROWS = [0, 1]

export interface ChatConversationProps {
  readonly messages: readonly RuntimeMessage[]
  readonly threadId: string
  readonly isLoadingHistory: boolean
  readonly isStreaming: boolean
  readonly onRetry: () => void
  readonly onRegenerate?: () => void
  readonly onContinueConversation?: (message: string) => void
  readonly onOpenUrl?: (url: string) => void
  /** HITL 表单提交：回答文本 + 结构化答案，交由运行时带 resume 续跑 */
  readonly onHitlSubmit?: (
    message: string,
    interrupt: HitlInterrupt,
    answer: Record<string, unknown>,
  ) => void
}

/**
 * 消息滚动区。
 *
 * 只在用户位于底部附近时跟随流式输出，避免阅读历史时被不断拉回底部；
 * 距离底部超过阈值后显示「回到最新」，把滚动控制权交还用户。
 */
export function ChatConversation({
  messages,
  threadId,
  isLoadingHistory,
  isStreaming,
  onRetry,
  onRegenerate,
  onContinueConversation,
  onOpenUrl,
  onHitlSubmit,
}: ChatConversationProps) {
  const { t } = useTranslation()
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const [isPinnedToBottom, setIsPinnedToBottom] = useState(true)

  const lastMessage = messages.at(-1)
  // 运行时已按帧合并 token，这里的依赖每个渲染帧最多变化一次
  const streamTick = lastMessage
    ? `${lastMessage.id}:${lastMessage.content.length}:${lastMessage.reasoning.length}:${lastMessage.steps.length}`
    : ''

  const scrollToBottom = useCallback((smooth = false): void => {
    const element = scrollRef.current
    if (!element) {
      return
    }
    element.scrollTo({ top: element.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  }, [])

  // 在浏览器绘制前完成贴底滚动：否则新内容会先绘制在可视区外再被拉回，
  // 表现为一帧抖动；同时只在用户贴底时读取 scrollHeight，避免打断阅读。
  useLayoutEffect(() => {
    if (isPinnedToBottom) {
      scrollToBottom()
    }
  }, [streamTick, isPinnedToBottom, scrollToBottom])

  const handleScroll = (): void => {
    const element = scrollRef.current
    if (!element) {
      return
    }
    setIsPinnedToBottom(
      element.scrollHeight - element.scrollTop - element.clientHeight < PIN_THRESHOLD,
    )
  }

  const isEmpty = messages.length === 0 && !isLoadingHistory
  const lastAssistant = messages.filter((message) => message.role === 'assistant').at(-1)
  const canRetry =
    !isStreaming &&
    lastMessage?.role === 'assistant' &&
    (lastMessage.status === 'error' || lastMessage.status === 'cancelled')
  // 只有最后一条已完成的回答可以重新生成，避免误替换历史回答
  const canRegenerate =
    !isStreaming && lastMessage?.role === 'assistant' && lastMessage.status === 'done'

  /** 只播报阶段变化，不逐字朗读流式 token */
  const resolveAnnouncement = (): string => {
    if (isStreaming) {
      return t('chat.status.streaming')
    }
    switch (lastAssistant?.status) {
      case 'done':
        return t('chat.live.done')
      case 'cancelled':
        return t('chat.status.cancelled')
      case 'error':
        return t('chat.status.error')
      default:
        return ''
    }
  }
  const liveAnnouncement = resolveAnnouncement()

  // 始终预留滚动条槽位：否则流式内容撑出滚动条时可用宽度骤减 10px，
  // 居中的消息会整体左移并重新换行；both-edges 让左右槽位对称，
  // 保证消息区中轴与下方输入框一致
  return (
    <div
      ref={scrollRef}
      className="min-h-0 flex-1 overflow-y-auto [scrollbar-gutter:stable_both-edges]"
      onScroll={handleScroll}
    >
      {/* 窄屏顶部留出悬浮导航入口的空间，避免消息与按钮重叠。
                外层不锁版心也不留底部内边距：空态需要把「为你推荐」贴到输入框上方，
                边距由各分支自己控制。 */}
      <div className="flex min-h-full w-full flex-col px-4 pt-12 sm:px-8 sm:pt-6">
        <div className="sr-only" aria-live="polite">
          {liveAnnouncement}
        </div>

        {isLoadingHistory ? (
          <div
            className="mx-auto w-full max-w-[var(--app-content-width)] space-y-8"
            aria-hidden="true"
          >
            {SKELETON_ROWS.map((row) => (
              <div key={row} className="space-y-2">
                <div className="skeleton h-3 w-24" />
                <div className="skeleton h-3 w-full" />
                <div className="skeleton h-3 w-4/5" />
                <div className="skeleton h-3 w-2/3" />
              </div>
            ))}
          </div>
        ) : isEmpty ? (
          <ChatEmptyState
            {...(onContinueConversation ? { onSelectExample: onContinueConversation } : {})}
          />
        ) : (
          <div className="mx-auto w-full max-w-[var(--app-content-width)] space-y-6 pb-10">
            {messages.map((message) => (
              <MessageItem
                key={message.id}
                message={message}
                threadId={threadId}
                canRetry={canRetry && message.id === lastMessage?.id}
                onRetry={onRetry}
                canRegenerate={canRegenerate && message.id === lastMessage?.id}
                {...(onRegenerate ? { onRegenerate } : {})}
                {...(onContinueConversation ? { onContinueConversation } : {})}
                {...(onOpenUrl ? { onOpenUrl } : {})}
                {...(onHitlSubmit ? { onHitlSubmit } : {})}
              />
            ))}
          </div>
        )}

        {!isPinnedToBottom ? (
          <div className="pointer-events-none sticky bottom-3 z-10 flex justify-center">
            <Button
              variant="outline"
              size="sm"
              className="pointer-events-auto gap-1 shadow-sm"
              onClick={() => scrollToBottom(true)}
            >
              <ArrowDown className="size-3.5" />
              {t('chat.scrollToLatest')}
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  )
}
