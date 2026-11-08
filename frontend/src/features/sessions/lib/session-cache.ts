import type { QueryClient } from '@tanstack/react-query'

import { queryKeys } from '@/shared/lib/query-keys'
import type { PageResult } from '@/shared/types/http'

import type { SessionSummary } from '../api/types'

/**
 * 与服务端 `ORDER BY is_pinned DESC, last_active_at DESC` 保持一致的排序。
 *
 * 乐观更新后必须先按服务端规则重排，否则置顶项会停在原位置，
 * 用户仍然看不到「点击置顶」的变化。
 */
export const sortSessionSummaries = (
  sessions: readonly SessionSummary[],
): SessionSummary[] =>
  [...sessions].sort((left, right) => {
    const leftPinned = Boolean(left.is_pinned)
    const rightPinned = Boolean(right.is_pinned)
    if (leftPinned !== rightPinned) {
      return leftPinned ? -1 : 1
    }
    return right.last_active_at.localeCompare(left.last_active_at)
  })

/** 就地更新所有已缓存的会话列表（含默认与归档分页），未缓存的分页保持不变 */
export const updateCachedSessionLists = (
  queryClient: QueryClient,
  updater: (list: SessionSummary[]) => SessionSummary[],
): void => {
  queryClient.setQueriesData<PageResult<SessionSummary>>(
    { queryKey: queryKeys.sessions.lists },
    (previous) => (previous ? { ...previous, list: updater(previous.list) } : previous),
  )
}
