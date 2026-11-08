import { memo, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Check, Copy, RefreshCw, RotateCcw } from 'lucide-react'

import { useAppStore } from '@/app/stores/app-store'
import { Button } from '@/shared/ui/button'
import { formatMessageTimestamp } from '@/shared/lib/format'
import { cn } from '@/shared/lib/utils'

import type { ChatMessageStatus, RuntimeMessage } from '../runtime/types'
import { ExecutionTrace } from './execution-trace'
import { MessageContent } from './message-content'
import { ReasoningPanel } from './reasoning-panel'

const STATUS_LABEL_KEYS: Record<ChatMessageStatus, string | null> = {
    pending: 'chat.status.pending',
    streaming: 'chat.status.streaming',
    done: null,
    cancelled: 'chat.status.cancelled',
    error: 'chat.status.error',
}

const COPY_FEEDBACK_MS = 1600

export interface MessageItemProps {
    readonly message: RuntimeMessage
    /** 会话 ID 只用于生成式 UI 的表单状态键，用户消息不依赖 */
    readonly threadId: string
    /** 仅最后一条助手消息允许重试，避免重发历史问题 */
    readonly canRetry?: boolean
    readonly onRetry?: () => void
    /** 仅最后一条已完成的助手消息允许重新生成 */
    readonly canRegenerate?: boolean
    readonly onRegenerate?: () => void
    readonly onContinueConversation?: (message: string) => void
    readonly onOpenUrl?: (url: string) => void
}

/**
 * 单条消息。
 *
 * 用户消息右对齐成气泡；助手回答占满阅读宽度，工具轨迹与 Markdown 都在这条消息
 * 内部完成。复制与重试只在有内容/可重试时出现，避免对历史消息重复发问。
 *
 * 用 `memo` 固定渲染边界：流式期间只有最后一条消息的对象引用会变化，
 * 历史消息因此不会在每个 token 上重复执行组件函数与 Markdown 解析。
 */
function MessageItemComponent({
    message,
    threadId,
    canRetry = false,
    onRetry,
    canRegenerate = false,
    onRegenerate,
    onContinueConversation,
    onOpenUrl,
}: MessageItemProps) {
    const { t } = useTranslation()
    const showTimestamps = useAppStore((state) => state.showTimestamps)
    const [isCopied, setIsCopied] = useState(false)
    const copyTimerRef = useRef<number | undefined>(undefined)

    useEffect(
        () => () => {
            window.clearTimeout(copyTimerRef.current)
        },
        [],
    )

    if (message.role === 'user') {
        return (
            <div className="flex justify-end" data-message-role="user">
                <div className="max-w-[var(--cds-message-bubble-measure)] whitespace-pre-wrap break-words rounded-[var(--cds-message-bubble-radius)] rounded-br-[var(--cds-message-bubble-radius-meeting)] bg-secondary px-4 py-3 text-[0.9375rem] leading-relaxed text-secondary-foreground">
                    {message.content}
                </div>
            </div>
        )
    }

    const isLive = message.status === 'pending' || message.status === 'streaming'
    const statusLabelKey = STATUS_LABEL_KEYS[message.status]
    const canCopy = Boolean(message.content.trim())

    const handleCopy = async (): Promise<void> => {
        try {
            await navigator.clipboard.writeText(message.content)
            setIsCopied(true)
            window.clearTimeout(copyTimerRef.current)
            copyTimerRef.current = window.setTimeout(() => setIsCopied(false), COPY_FEEDBACK_MS)
        } catch {
            toast.error(t('chat.copyFailed'))
        }
    }

    return (
        <div className="group" data-message-role="assistant">
            <div className="min-w-0">
                {statusLabelKey ? (
                    <div className="mb-1.5 flex h-6 items-center gap-2">
                        <span
                            className={cn(
                                'text-[0.6875rem]',
                                message.status === 'error'
                                    ? 'text-destructive'
                                    : 'text-muted-foreground',
                            )}
                        >
                            {t(statusLabelKey)}
                        </span>
                    </div>
                ) : null}

                <ReasoningPanel text={message.reasoning} live={isLive} />

                <ExecutionTrace steps={message.steps} live={isLive} />

                {message.content ? (
                    <MessageContent
                        content={message.content}
                        status={message.status}
                        threadId={threadId}
                        {...(onContinueConversation ? { onContinueConversation } : {})}
                        {...(onOpenUrl ? { onOpenUrl } : {})}
                    />
                ) : isLive && !message.reasoning ? (
                    <p className="mt-1 text-sm text-muted-foreground">
                        {t('chat.status.waiting')}
                        <span
                            className="stream-caret ml-0.5 inline-block h-3.5 w-px align-[-0.15em]"
                            aria-hidden="true"
                        />
                    </p>
                ) : null}

                {message.status === 'cancelled' && message.content ? (
                    <p className="mt-2 text-xs text-muted-foreground">
                        {t('chat.status.cancelledHint')}
                    </p>
                ) : null}

                {showTimestamps && message.status === 'done' && message.createdAt > 0 ? (
                    <time
                        className="mt-1 block text-[0.6875rem] text-muted-foreground"
                        dateTime={new Date(message.createdAt).toISOString()}
                    >
                        {formatMessageTimestamp(message.createdAt)}
                    </time>
                ) : null}

                <div className="mt-2 flex h-7 items-center gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100 max-md:opacity-100">
                    {canCopy ? (
                        <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label={t('chat.copy')}
                            onClick={() => void handleCopy()}
                        >
                            {isCopied ? (
                                <Check className="size-3.5 text-success" />
                            ) : (
                                <Copy className="size-3.5" />
                            )}
                        </Button>
                    ) : null}

                    {canRegenerate && onRegenerate ? (
                        <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label={t('chat.regenerate')}
                            onClick={onRegenerate}
                        >
                            <RefreshCw className="size-3.5" />
                        </Button>
                    ) : null}

                    {canRetry && onRetry ? (
                        <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label={t('chat.retry')}
                            onClick={onRetry}
                        >
                            <RotateCcw className="size-3.5" />
                        </Button>
                    ) : null}
                </div>
            </div>
        </div>
    )
}

export const MessageItem = memo(MessageItemComponent)
