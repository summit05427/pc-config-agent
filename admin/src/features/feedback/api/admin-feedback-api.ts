import { z } from 'zod'
import { queryOptions } from '@tanstack/react-query'
import { httpBlob, httpJson } from '@/core/http/client'
import type { PageResult } from '@/core/http/types'
import { saveBlob } from '@/lib/download'
import { queryKeys } from '@/lib/query-keys'
import {
  FEEDBACK_RATINGS,
  FEEDBACK_REASONS,
  type AdminFeedbackItem,
  type AdminFeedbackSummary,
  type FeedbackRating,
  type FeedbackReason,
} from '../types'

const feedbackItemSchema = z.object({
  userId: z.string(),
  username: z
    .string()
    .nullish()
    .transform((value) => value ?? null),
  threadId: z.string(),
  messageId: z.string(),
  rating: z.enum(FEEDBACK_RATINGS),
  reasonCode: z
    .enum(FEEDBACK_REASONS)
    .nullish()
    .transform((value) => value ?? null),
  comment: z
    .string()
    .nullish()
    .transform((value) => value ?? null),
  createdAt: z.string().min(1),
})

const feedbackPageSchema = z.object({
  list: z.array(feedbackItemSchema),
  total: z.number(),
  page: z.number(),
  size: z.number(),
})

const reasonCountSchema = z.object({
  reasonCode: z.enum(FEEDBACK_REASONS),
  label: z.string(),
  total: z.number(),
})

const feedbackSummarySchema = z.object({
  upCount: z.number(),
  downCount: z.number(),
  reasons: z.array(reasonCountSchema),
})

export interface AdminFeedbackParams {
  page: number
  size: number
  rating?: FeedbackRating | ''
  reasonCode?: FeedbackReason | ''
  userId?: string
  threadId?: string
  from?: string
  to?: string
}

/**
 * 把页面搜索参数收敛成接口参数。
 *
 * 空串表示「不过滤」，必须转成 undefined 才不会作为 `rating=` 发给后端；
 * 列表、统计、导出三个接口共用同一套过滤口径。
 */
function toFilterParams(params: AdminFeedbackParams): Record<string, string | undefined> {
  return {
    rating: params.rating || undefined,
    reasonCode: params.reasonCode || undefined,
    userId: params.userId || undefined,
    threadId: params.threadId || undefined,
    from: params.from || undefined,
    to: params.to || undefined,
  }
}

/** 反馈列表：过滤与分页均由服务端执行，按提交时间倒序。 */
export async function fetchAdminFeedback(
  params: AdminFeedbackParams
): Promise<PageResult<AdminFeedbackItem>> {
  return feedbackPageSchema.parse(
    await httpJson<unknown>({
      url: '/admin/feedback',
      method: 'get',
      params: {
        page: params.page,
        size: params.size,
        ...toFilterParams(params),
      },
    })
  )
}

export const adminFeedbackListQueryOptions = (params: AdminFeedbackParams) =>
  queryOptions({
    queryKey: [...queryKeys.adminFeedback.all, 'list', params],
    queryFn: () => fetchAdminFeedback(params),
  })

/** 反馈统计：赞踩总数与踩的原因分布，口径与列表完全一致。 */
export async function fetchFeedbackSummary(
  params: AdminFeedbackParams
): Promise<AdminFeedbackSummary> {
  return feedbackSummarySchema.parse(
    await httpJson<unknown>({
      url: '/admin/feedback/summary',
      method: 'get',
      params: toFilterParams(params),
    })
  )
}

export const adminFeedbackSummaryQueryOptions = (params: AdminFeedbackParams) =>
  queryOptions({
    queryKey: [...queryKeys.adminFeedback.all, 'summary', params],
    queryFn: () => fetchFeedbackSummary(params),
  })

function formatFileTime(date: Date): string {
  const pad = (value: number): string => String(value).padStart(2, '0')
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`
}

/**
 * 按当前筛选导出 CSV。
 *
 * 必须走 XHR 而非直接打开链接：访问令牌只存在于内存，无法随浏览器导航发出；
 * 服务端已在文件内容前写入 UTF-8 BOM，Excel 可直接打开。
 */
export async function exportFeedbackCsv(params: AdminFeedbackParams): Promise<void> {
  const blob = await httpBlob({
    url: '/admin/feedback/export',
    method: 'get',
    params: toFilterParams(params),
  })
  saveBlob(blob, `feedback-${formatFileTime(new Date())}.csv`)
}
