/** 评分方向，与 Java `FeedbackRating` 枚举同名。 */
export const FEEDBACK_RATINGS = ['UP', 'DOWN'] as const
export type FeedbackRating = (typeof FEEDBACK_RATINGS)[number]

/** 踩的原因，与 Java `FeedbackReason` 枚举同名；顺序即后台展示顺序。 */
export const FEEDBACK_REASONS = [
  'INACCURATE',
  'OFF_TOPIC',
  'INCOMPLETE',
  'FORMAT',
  'UNSAFE',
  'OTHER',
] as const
export type FeedbackReason = (typeof FEEDBACK_REASONS)[number]

export const RATING_LABELS: Record<FeedbackRating, string> = {
  UP: '赞',
  DOWN: '踩',
}

export const REASON_LABELS: Record<FeedbackReason, string> = {
  INACCURATE: '信息不准确',
  OFF_TOPIC: '答非所问',
  INCOMPLETE: '回答不完整',
  FORMAT: '格式混乱',
  UNSAFE: '内容不当',
  OTHER: '其他',
}

/** 管理端反馈列表项；`username` 与 `comment` 可能为空。 */
export interface AdminFeedbackItem {
  userId: string
  username: string | null
  threadId: string
  messageId: string
  rating: FeedbackRating
  reasonCode: FeedbackReason | null
  comment: string | null
  createdAt: string
}

export interface FeedbackReasonCount {
  reasonCode: FeedbackReason
  label: string
  total: number
}

export interface AdminFeedbackSummary {
  upCount: number
  downCount: number
  reasons: FeedbackReasonCount[]
}

export function getRatingLabel(rating: FeedbackRating): string {
  return RATING_LABELS[rating]
}

/** 原因缺失时返回占位符而不是空串，让表格列保持可读。 */
export function getReasonLabel(reason: FeedbackReason | null): string {
  return reason ? REASON_LABELS[reason] : '—'
}
