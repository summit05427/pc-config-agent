import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight } from 'lucide-react'

import { sessionsListQueryOptions } from '@/features/sessions/api'
import { SessionList } from '@/features/sessions/components/session-list'
import { ROUTE_PATHS } from '@/routes/paths'

const PAGE_SIZE = 20
const PINNED_LIST_ID = 'sidebar-pinned-sessions'
const RECENT_LIST_ID = 'sidebar-recent-sessions'

export interface SidebarSessionListProps {
    /** 折叠态只保留占位，把底部工具保持在最下方 */
    readonly collapsed: boolean
}

interface SessionGroupProps {
    readonly listId: string
    readonly title: string
    readonly expandLabel: string
    readonly collapseLabel: string
    readonly isOpen: boolean
    readonly onToggle: () => void
    readonly children: ReactNode
}

/** 可折叠分组标题；置顶与最近共用同一套交互与样式 */
function SessionGroup({
    listId,
    title,
    expandLabel,
    collapseLabel,
    isOpen,
    onToggle,
    children,
}: SessionGroupProps) {
    return (
        <div className="pt-1 first:pt-0">
            <button
                type="button"
                aria-expanded={isOpen}
                aria-controls={listId}
                aria-label={isOpen ? collapseLabel : expandLabel}
                className="flex h-[var(--control-height-sm)] w-full items-center gap-1 rounded-[var(--cds-radius-btn-xs)] px-2 text-xs font-medium tracking-wide text-muted-foreground transition-colors hover:bg-sidebar-accent/70 hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/35"
                onClick={onToggle}
            >
                <span className="min-w-0 flex-1 text-left">{title}</span>
                {isOpen ? (
                    <ChevronDown className="size-3.5 shrink-0" aria-hidden="true" />
                ) : (
                    <ChevronRight className="size-3.5 shrink-0" aria-hidden="true" />
                )}
            </button>

            {isOpen ? <div id={listId}>{children}</div> : null}
        </div>
    )
}

/**
 * 侧栏会话列表。
 *
 * 服务端已按「置顶优先 + 最近活跃」排好序，这里只做分组展示：
 * 置顶项单独成组，其余进入「最近」，两组都可独立折叠。
 * 点击条目走规范 URL，删除或归档当前会话后回退到新对话页。
 */
export function SidebarSessionList({ collapsed }: SidebarSessionListProps) {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const params = useParams({ strict: false })
    const sessionsQuery = useQuery(sessionsListQueryOptions(1, PAGE_SIZE))
    const [isPinnedOpen, setIsPinnedOpen] = useState(true)
    const [isRecentOpen, setIsRecentOpen] = useState(true)

    if (collapsed) {
        return <div className="flex-1" aria-hidden="true" />
    }

    const activeThreadId = params.sessionId
    const sessions = sessionsQuery.data?.list ?? []
    const pinnedSessions = sessions.filter((session) => session.is_pinned)
    const recentSessions = sessions.filter((session) => !session.is_pinned)

    const openSession = (threadId: string): void => {
        void navigate({ to: '/chat/$sessionId', params: { sessionId: threadId } })
    }

    const leaveIfActive = (threadId: string): void => {
        if (threadId === activeThreadId) {
            void navigate({ to: ROUTE_PATHS.chatNew })
        }
    }

    return (
        <div className="flex min-h-0 flex-1 flex-col">
            {/* 侧栏滚动条永久隐藏但仍可滚动：既不占用内容宽度，
                也不会在列表刚好溢出时因滚动条出现而挤窄内容造成抖动 */}
            <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                {pinnedSessions.length > 0 ? (
                    <SessionGroup
                        listId={PINNED_LIST_ID}
                        title={t('chat.sessions.pinned')}
                        expandLabel={t('chat.sessions.expandPinned')}
                        collapseLabel={t('chat.sessions.collapsePinned')}
                        isOpen={isPinnedOpen}
                        onToggle={() => setIsPinnedOpen((isOpen) => !isOpen)}
                    >
                        <SessionList
                            sessions={pinnedSessions}
                            emptyMessageKey="chat.sessions.empty"
                            showActions
                            activeThreadId={activeThreadId}
                            onSelect={openSession}
                            onDeleted={leaveIfActive}
                            onArchived={leaveIfActive}
                        />
                    </SessionGroup>
                ) : null}

                {/* 无会话时仍需渲染「最近」分组，由 SessionList 承担加载/错误/空态 */}
                {recentSessions.length > 0 || sessions.length === 0 ? (
                    <SessionGroup
                        listId={RECENT_LIST_ID}
                        title={t('chat.sessions.title')}
                        expandLabel={t('chat.sessions.expand')}
                        collapseLabel={t('chat.sessions.collapse')}
                        isOpen={isRecentOpen}
                        onToggle={() => setIsRecentOpen((isOpen) => !isOpen)}
                    >
                        <SessionList
                            sessions={recentSessions}
                            isLoading={sessionsQuery.isLoading}
                            errorMessage={sessionsQuery.isError ? t('common.loadFailed') : undefined}
                            emptyMessageKey="chat.sessions.empty"
                            showActions
                            activeThreadId={activeThreadId}
                            onSelect={openSession}
                            onDeleted={leaveIfActive}
                            onArchived={leaveIfActive}
                            onRetry={() => void sessionsQuery.refetch()}
                        />
                    </SessionGroup>
                ) : null}
            </div>
        </div>
    )
}
