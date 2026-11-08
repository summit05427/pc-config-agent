import { useTranslation } from 'react-i18next'

import { Button } from '@/shared/ui/button'
import { Skeleton } from '@/shared/ui/skeleton'

import type { SessionSummary } from '../api/types'
import { SessionListItem } from './session-list-item'

export interface SessionListProps {
    sessions: readonly SessionSummary[]
    isLoading?: boolean
    /** 已翻译或服务端返回的错误文案；为空表示没有错误 */
    errorMessage?: string
    /** 空态词条 key，由调用页面决定具体措辞 */
    emptyMessageKey: string
    /** 侧栏展示「⋯」操作菜单；欢迎页保持只读行样式 */
    showActions?: boolean
    /** 当前会话，用于侧栏高亮与删除后的地址回退 */
    activeThreadId?: string
    onSelect: (threadId: string) => void
    onDeleted?: (threadId: string) => void
    onArchived?: (threadId: string) => void
    onRetry?: () => void
}

const SKELETON_WIDTHS = ['w-2/3', 'w-1/2', 'w-3/5'] as const

/**
 * 会话列表展示层。
 *
 * 只负责四种视觉状态（加载、错误、空、列表），不直接请求数据；
 * 侧栏与欢迎页共用，避免各写一套空态与重试逻辑。
 */
export function SessionList({
    sessions,
    isLoading = false,
    errorMessage,
    emptyMessageKey,
    showActions = false,
    activeThreadId,
    onSelect,
    onDeleted,
    onArchived,
    onRetry,
}: SessionListProps) {
    const { t } = useTranslation()

    // 四种状态共用同一个根节点：从空态切到列表时只替换内部内容，
    // 不重建整块容器，减少首条会话落库瞬间的布局跳变
    return (
        <div>
            {isLoading ? (
                <div className="mt-3 space-y-2" aria-hidden="true">
                    {SKELETON_WIDTHS.map((widthClass) => (
                        <div key={widthClass} className="flex items-center gap-2 px-1">
                            <Skeleton className="size-3.5 rounded" />
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
                    {sessions.map((session) => (
                        <li key={session.thread_id}>
                            <SessionListItem
                                session={session}
                                isActive={session.thread_id === activeThreadId}
                                showActions={showActions}
                                onSelect={onSelect}
                                onDeleted={onDeleted}
                                onArchived={onArchived}
                            />
                        </li>
                    ))}
                </ul>
            )}
        </div>
    )
}
