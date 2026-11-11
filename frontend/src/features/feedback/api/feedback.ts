import { queryOptions } from '@tanstack/react-query'

import { http } from '@/core/http'
import { queryKeys } from '@/shared/lib/query-keys'

/** 评价方向；与 Java `FeedbackRating` 枚举同名，直接作为请求体发送 */
export type FeedbackRating = 'UP' | 'DOWN'

/** 踩的原因分类；取值必须与 Java `FeedbackReason` 保持一致，否则服务端返回 reason_invalid */
export type FeedbackReason =
  | 'INACCURATE'
  | 'OFF_TOPIC'
  | 'INCOMPLETE'
  | 'FORMAT'
  | 'UNSAFE'
  | 'OTHER'

/** 原因按产品意图排序：先「答错」，再「答偏」「答不全」，最后是格式与安全 */
export const FEEDBACK_REASONS: readonly FeedbackReason[] = [
  'INACCURATE',
  'OFF_TOPIC',
  'INCOMPLETE',
  'FORMAT',
  'UNSAFE',
  'OTHER',
]

/** 打开尝试反馈面板时的默认选中项，避免用户必须多点一次 */
export const DEFAULT_FEEDBACK_REASON: FeedbackReason = 'INACCURATE'

/** 服务端返回的本人评价；`reasonCode` 仅在踩时存在 */
export interface MessageFeedback {
  messageId: string
  rating: FeedbackRating
  reasonCode: FeedbackReason | null
}

export interface UpsertMessageFeedbackPayload {
  threadId: string
  rating: FeedbackRating
  /** 点赞会被服务端归一化为 null，这里允许省略 */
  reasonCode?: FeedbackReason | null
  comment?: string | null
}

/**
 * 读取本人在某个会话下的全部评价。
 *
 * 刷新页面后靠它恢复赞踩高亮；接口失败时静默降级（按钮仍可点击，只是不显示历史状态），
 * 不能让一次失败的查询把整个消息区打成错误态。
 */
export const listThreadFeedback = (threadId: string): Promise<MessageFeedback[]> =>
  http.get<MessageFeedback[]>('/feedback', { params: { threadId }, silent: true })

/**
 * 提交或覆盖一条评价。
 *
 * 使用 PUT：同一条消息对同一用户只保留一条记录，重复提交即覆盖。
 * `messageId` 只由 `[A-Za-z0-9_.:-]` 组成，可直接拼进路径，不需要再做 URL 编码。
 */
export const upsertMessageFeedback = (
  messageId: string,
  payload: UpsertMessageFeedbackPayload,
): Promise<MessageFeedback> => http.put<MessageFeedback>(`/messages/${messageId}/feedback`, payload)

/** 取消本人对某条消息的评价；服务端找不到记录时返回 40402 */
export const deleteMessageFeedback = (messageId: string): Promise<void> =>
  http.delete<void>(`/messages/${messageId}/feedback`)

/** 会话级评价列表：同一会话内所有消息共用一次查询，避免逐条消息各发一次请求 */
export const threadFeedbackQueryOptions = (threadId: string) =>
  queryOptions({
    queryKey: queryKeys.feedback.thread(threadId),
    queryFn: () => listThreadFeedback(threadId),
  })
