import { MessageSquare } from 'lucide-react'

import { formatSessionTimestamp } from '@/shared/lib/format'
import { cn } from '@/shared/lib/utils'

import type { SessionSummary } from '../api/types'
import { SessionActions } from './session-actions'

const SHORT_THREAD_ID_LENGTH = 6

/** 服务端标题优先；尚未生成标题（如新会话）时退回短 ID，不伪造内容 */
export const labelForSession = (session: SessionSummary): string =>
  session.title?.trim() || `#${session.thread_id.slice(0, SHORT_THREAD_ID_LENGTH)}`

export interface SessionListItemProps {
  readonly session: SessionSummary
  readonly isActive?: boolean
  /** 侧栏开启操作菜单；欢迎页保持「图标 + 标题 + 时间」的只读样式 */
  readonly showActions?: boolean
  readonly onSelect: (threadId: string) => void
  readonly onDeleted?: (threadId: string) => void
  readonly onArchived?: (threadId: string) => void
}

/**
 * 会话行。
 *
 * 行主体与操作按钮是同级元素而不是嵌套按钮，避免出现 button 套 button
 * 导致的键盘与读屏异常；菜单只在侧栏启用。
 */
export function SessionListItem({
  session,
  isActive = false,
  showActions = false,
  onSelect,
  onDeleted,
  onArchived,
}: SessionListItemProps) {
  return (
    <div
      className={cn(
        'group flex items-center gap-1 rounded-[var(--cds-radius-btn-xs)] transition-colors hover:bg-muted focus-within:bg-muted',
        isActive && 'bg-sidebar-accent',
      )}
    >
      <button
        type="button"
        aria-current={isActive ? 'page' : undefined}
        className="flex h-[var(--app-sidebar-row-height)] min-w-0 flex-1 items-center gap-2 rounded-[var(--cds-radius-btn-xs)] px-2 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring/35"
        onClick={() => onSelect(session.thread_id)}
      >
        {showActions ? null : (
          <MessageSquare className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
        )}
        <span
          className={cn(
            'min-w-0 flex-1 truncate text-nav',
            isActive ? 'font-medium text-sidebar-accent-foreground' : 'text-foreground/90',
          )}
        >
          {labelForSession(session)}
        </span>
      </button>

      {showActions ? (
        // 操作入口默认隐藏，悬浮或键盘聚焦该行时才出现，避免列表被「⋯」占满
        <div className="pointer-events-none opacity-0 transition-opacity duration-150 group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100 [@media(hover:none)]:pointer-events-auto [@media(hover:none)]:opacity-100">
          <SessionActions session={session} onDeleted={onDeleted} onArchived={onArchived} />
        </div>
      ) : (
        <span className="tabular shrink-0 pr-2 text-xs text-muted-foreground">
          {formatSessionTimestamp(session.last_active_at)}
        </span>
      )}
    </div>
  )
}
