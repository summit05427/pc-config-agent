import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ThumbsDown, ThumbsUp } from 'lucide-react'
import { toast } from 'sonner'

import { useAuthSessionStore } from '@/features/auth/model/auth-session'
import {
  DEFAULT_FEEDBACK_REASON,
  FEEDBACK_REASONS,
  deleteMessageFeedback,
  threadFeedbackQueryOptions,
  upsertMessageFeedback,
  type FeedbackRating,
  type FeedbackReason,
  type UpsertMessageFeedbackPayload,
} from '@/features/feedback/api'
import { Button } from '@/shared/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/ui/popover'
import { Textarea } from '@/shared/ui/textarea'
import { queryKeys } from '@/shared/lib/query-keys'
import { cn } from '@/shared/lib/utils'

/** 与服务端 `UpsertMessageFeedbackRequest.comment` 的长度上限保持一致 */
const MAX_COMMENT_LENGTH = 500

export interface MessageFeedbackProps {
  /** 服务端稳定消息标识；缺失（旧服务端）时不提供反馈入口 */
  readonly messageId?: string
  readonly threadId: string
}

/**
 * 消息级赞 / 踩的入口。
 *
 * 未登录或服务端没有下发 `message_id` 时直接不渲染：内部组件会发查询，
 * 而这两类消息既无法提交也无法恢复状态，挂载只会多一次必然失败的请求。
 */
export function MessageFeedback({ messageId, threadId }: MessageFeedbackProps) {
  const isAuthenticated = useAuthSessionStore((state) => state.status === 'authenticated')

  if (!messageId || !isAuthenticated) {
    return null
  }
  return <MessageFeedbackActions messageId={messageId} threadId={threadId} />
}

/** 点赞一次即提交；踩需要选择原因，因此只有踩会展开面板。 */
function MessageFeedbackActions({
  messageId,
  threadId,
}: {
  readonly messageId: string
  readonly threadId: string
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [isComposerOpen, setIsComposerOpen] = useState(false)
  const [reasonCode, setReasonCode] = useState<FeedbackReason>(DEFAULT_FEEDBACK_REASON)
  const [comment, setComment] = useState('')

  // 同一会话的评价只查一次，逐条消息从结果里挑自己的那条
  const { data } = useQuery(threadFeedbackQueryOptions(threadId))
  const current = data?.find((item) => item.messageId === messageId)

  const refreshFeedback = async (): Promise<void> => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.feedback.thread(threadId) })
  }

  const saveFeedback = useMutation({
    mutationFn: (payload: Omit<UpsertMessageFeedbackPayload, 'threadId'>) =>
      upsertMessageFeedback(messageId, { threadId, ...payload }),
    onSuccess: refreshFeedback,
    onError: () => toast.error(t('chat.feedback.failed')),
  })

  const removeFeedback = useMutation({
    mutationFn: () => deleteMessageFeedback(messageId),
    onSuccess: refreshFeedback,
    onError: () => toast.error(t('chat.feedback.failed')),
  })

  const isBusy = saveFeedback.isPending || removeFeedback.isPending
  const rating = current?.rating ?? null

  const applyRating = (next: FeedbackRating, onDone?: () => void): void => {
    saveFeedback.mutate(
      { rating: next },
      {
        onSuccess: () => {
          onDone?.()
          toast.success(t('chat.feedback.thanks'))
        },
      },
    )
  }

  const handleThumbsUp = (): void => {
    if (isBusy) {
      return
    }
    // 再次点击已选中的赞表示撤销，与踩面板里的「移除反馈」等价
    if (rating === 'UP') {
      removeFeedback.mutate()
      return
    }
    applyRating('UP')
  }

  const openComposer = (): void => {
    setReasonCode(current?.reasonCode ?? DEFAULT_FEEDBACK_REASON)
    // 服务端不回传备注，重新打开时从空开始，避免把上一次备注误当成已保存内容
    setComment('')
    setIsComposerOpen(true)
  }

  const submitDislike = (): void => {
    saveFeedback.mutate(
      { rating: 'DOWN', reasonCode, comment: comment.trim() || null },
      {
        onSuccess: () => {
          setIsComposerOpen(false)
          setComment('')
          toast.success(t('chat.feedback.thanks'))
        },
      },
    )
  }

  const removeDislike = (): void => {
    removeFeedback.mutate(undefined, { onSuccess: () => setIsComposerOpen(false) })
  }

  return (
    <>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={t('chat.feedback.up')}
        aria-pressed={rating === 'UP'}
        disabled={isBusy}
        className={cn(rating === 'UP' && 'text-primary')}
        onClick={handleThumbsUp}
      >
        <ThumbsUp className={cn('size-3.5', rating === 'UP' && 'fill-current')} />
      </Button>

      <Popover open={isComposerOpen} onOpenChange={setIsComposerOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={t('chat.feedback.down')}
            aria-pressed={rating === 'DOWN'}
            disabled={isBusy}
            className={cn(rating === 'DOWN' && 'text-destructive')}
            onClick={openComposer}
          >
            <ThumbsDown className={cn('size-3.5', rating === 'DOWN' && 'fill-current')} />
          </Button>
        </PopoverTrigger>

        <PopoverContent align="start" side="bottom" className="w-80">
          <div className="flex flex-col gap-3">
            <p className="text-sm font-medium">{t('chat.feedback.title')}</p>

            <div
              role="group"
              aria-label={t('chat.feedback.reasonLabel')}
              className="grid grid-cols-2 gap-1.5"
            >
              {FEEDBACK_REASONS.map((reason) => (
                <Button
                  key={reason}
                  type="button"
                  size="xs"
                  variant={reason === reasonCode ? 'secondary' : 'outline'}
                  aria-pressed={reason === reasonCode}
                  onClick={() => setReasonCode(reason)}
                >
                  {t(`chat.feedback.reasons.${reason}`)}
                </Button>
              ))}
            </div>

            <label className="flex flex-col gap-1.5 text-xs text-muted-foreground">
              {t('chat.feedback.commentLabel')}
              <Textarea
                value={comment}
                maxLength={MAX_COMMENT_LENGTH}
                rows={3}
                placeholder={t('chat.feedback.commentPlaceholder')}
                onChange={(event) => setComment(event.target.value)}
              />
            </label>

            <div className="flex items-center justify-between gap-2">
              {rating === 'DOWN' ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  disabled={isBusy}
                  onClick={removeDislike}
                >
                  {t('chat.feedback.remove')}
                </Button>
              ) : (
                <span />
              )}
              <div className="flex items-center gap-1.5">
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  onClick={() => setIsComposerOpen(false)}
                >
                  {t('chat.feedback.cancel')}
                </Button>
                <Button type="button" size="xs" disabled={isBusy} onClick={submitDislike}>
                  {t('chat.feedback.submit')}
                </Button>
              </div>
            </div>
          </div>
        </PopoverContent>
      </Popover>
    </>
  )
}
