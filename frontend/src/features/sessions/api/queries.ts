import { queryOptions } from '@tanstack/react-query'

import { queryKeys } from '@/shared/lib/query-keys'

import { getSessionMessages, listSessions } from './sessions'
import type { SessionMessageOrder } from './types'

/** 默认取最新一页 100 条，与 Vue 基线的 HISTORY_PAGE_SIZE 一致 */
const HISTORY_PAGE_SIZE = 100

/**
 * 会话列表查询选项。
 *
 * 使用 queryOptions 而不是在页面里拼对象，保证同一个分页参数只对应一个 key，
 * 轮询、失效与手动重试都能命中同一份缓存。
 */
export const sessionsListQueryOptions = (
  page: number,
  size: number,
  archived = false,
) =>
  queryOptions({
    queryKey: queryKeys.sessions.list(page, size, archived),
    queryFn: () => listSessions(page, size, archived),
  })

/**
 * 历史消息查询选项。
 *
 * 默认 desc：先看最新一页，长会话不必先翻到最后一页；
 * 调用方用同一个 key 预热、失效与重新同步，避免出现第二份历史缓存。
 */
export const sessionMessagesQueryOptions = (
  threadId: string,
  page = 1,
  size = HISTORY_PAGE_SIZE,
  order: SessionMessageOrder = 'desc',
) =>
  queryOptions({
    queryKey: queryKeys.sessions.messages(threadId, page, size, order),
    queryFn: () => getSessionMessages(threadId, page, size, order),
  })
