import { useCallback, useMemo, useState } from 'react'

interface SelectableSession {
  thread_id: string
}

export interface SessionSelection {
  selectedIds: ReadonlySet<string>
  isAllSelected: boolean
  toggle: (threadId: string) => void
  toggleAll: () => void
  clear: () => void
}

/**
 * 会话多选状态。
 *
 * 选择集合在渲染期按当前列表派生：列表刷新后已不存在的 ID 自动失效，
 * 批量操作不会命中已删除或已归档的会话；全选范围只限当前可见页。
 */
export const useSessionSelection = (
  sessions: readonly SelectableSession[],
): SessionSelection => {
  const [rawSelectedIds, setRawSelectedIds] = useState<ReadonlySet<string>>(() => new Set())

  const availableIds = useMemo(
    () => new Set(sessions.map((session) => session.thread_id)),
    [sessions],
  )

  const selectedIds = useMemo(
    () => new Set([...rawSelectedIds].filter((threadId) => availableIds.has(threadId))),
    [rawSelectedIds, availableIds],
  )

  const toggle = useCallback((threadId: string) => {
    setRawSelectedIds((previous) => {
      const next = new Set(previous)
      if (next.has(threadId)) {
        next.delete(threadId)
      } else {
        next.add(threadId)
      }
      return next
    })
  }, [])

  const toggleAll = useCallback(() => {
    setRawSelectedIds((previous) => {
      const validIds = [...previous].filter((threadId) => availableIds.has(threadId))
      return validIds.length === availableIds.size ? new Set() : new Set(availableIds)
    })
  }, [availableIds])

  const clear = useCallback(() => setRawSelectedIds(new Set()), [])

  return {
    selectedIds,
    isAllSelected: availableIds.size > 0 && selectedIds.size === availableIds.size,
    toggle,
    toggleAll,
    clear,
  }
}
