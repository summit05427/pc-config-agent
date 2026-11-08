import { useId, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Pin } from 'lucide-react'

import { formatSessionTimestamp } from '@/shared/lib/format'
import { cn } from '@/shared/lib/utils'
import { Button } from '@/shared/ui/button'
import { Checkbox } from '@/shared/ui/checkbox'
import { Skeleton } from '@/shared/ui/skeleton'

import type { SessionSummary } from '../api/types'
import { labelForSession } from './session-list-item'

const SKELETON_WIDTHS = ['w-2/3', 'w-1/2', 'w-3/5'] as const

export interface SelectableSessionListProps {
  readonly sessions: readonly SessionSummary[]
  readonly isLoading?: boolean
  /** 已翻译或服务端返回的错误文案；为空表示没有错误 */
  readonly errorMessage?: string
  readonly emptyMessageKey: string
  readonly selectedIds: ReadonlySet<string>
  readonly onToggle: (threadId: string) => void
  readonly onToggleAll: () => void
  readonly onOpen: (threadId: string) => void
  readonly onRetry?: () => void
  /** 批量操作按钮，与全选控件放在同一行 */
  readonly actions?: ReactNode
}

/**
 * 可多选的会话列表（设置页专用）。
 *
 * 与侧栏列表分开实现：这里的行首是复选框而不是菜单，勾选只影响批量操作，
 * 点击标题仍然进入会话；全选范围限定为当前页，避免误操作未加载的会话。
 */
export function SelectableSessionList({
  sessions,
  isLoading = false,
  errorMessage,
  emptyMessageKey,
  selectedIds,
  onToggle,
  onToggleAll,
  onOpen,
  onRetry,
  actions,
}: SelectableSessionListProps) {
  const { t } = useTranslation()
  const selectAllId = useId()
  const isAllSelected = sessions.length > 0 && selectedIds.size === sessions.length
  const isIndeterminate = selectedIds.size > 0 && !isAllSelected

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 rounded-[var(--cds-panel-radius)] border border-border px-3 py-2">
        <Checkbox
          id={selectAllId}
          checked={isIndeterminate ? 'indeterminate' : isAllSelected}
          disabled={sessions.length === 0}
          aria-label={t('settings.chats.selectAll')}
          onCheckedChange={onToggleAll}
        />
        <label htmlFor={selectAllId} className="text-xs text-muted-foreground">
          {t('settings.chats.selectedCount', { count: selectedIds.size })}
        </label>
        {actions ? (
          <div className="ml-auto flex flex-wrap items-center gap-2">{actions}</div>
        ) : null}
      </div>

      {isLoading ? (
        <div className="mt-3 space-y-2" aria-hidden="true">
          {SKELETON_WIDTHS.map((widthClass) => (
            <div key={widthClass} className="flex items-center gap-2 px-1">
              <Skeleton className="size-4 rounded" />
              <Skeleton className={`h-3.5 flex-1 ${widthClass}`} />
            </div>
          ))}
        </div>
      ) : errorMessage ? (
        <div className="mt-3 flex items-center gap-3 rounded-[var(--cds-panel-radius)] border border-border px-3 py-2.5">
          <p className="min-w-0 flex-1 text-xs leading-relaxed text-muted-foreground">
            {errorMessage}
          </p>
          {onRetry ? (
            <Button variant="outline" size="sm" onClick={onRetry}>
              {t('common.retry')}
            </Button>
          ) : null}
        </div>
      ) : sessions.length === 0 ? (
        <p className="mt-3 rounded-[var(--cds-panel-radius)] border border-dashed border-border px-3 py-6 text-center text-xs leading-relaxed text-muted-foreground">
          {t(emptyMessageKey)}
        </p>
      ) : (
        <ul className="mt-2 space-y-0.5">
          {sessions.map((session) => {
            const isSelected = selectedIds.has(session.thread_id)
            const label = labelForSession(session)
            return (
              <li key={session.thread_id}>
                <div
                  className={cn(
                    'flex items-center gap-2 rounded-[var(--cds-radius-btn-xs)] px-2 transition-colors hover:bg-muted',
                    isSelected && 'bg-muted',
                  )}
                >
                  <Checkbox
                    checked={isSelected}
                    aria-label={t('settings.chats.selectSession', { title: label })}
                    onCheckedChange={() => onToggle(session.thread_id)}
                  />

                  <button
                    type="button"
                    className="flex min-w-0 flex-1 items-center gap-2 py-2 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring/35"
                    onClick={() => onOpen(session.thread_id)}
                  >
                    {session.is_pinned ? (
                      <Pin className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                    ) : null}
                    <span className="min-w-0 flex-1 truncate text-nav text-foreground/90">
                      {label}
                    </span>
                  </button>

                  <span className="tabular shrink-0 pr-2 text-xs text-muted-foreground">
                    {formatSessionTimestamp(session.last_active_at)}
                  </span>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
