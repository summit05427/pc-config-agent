import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { BookOpenText, ChevronDown } from 'lucide-react'

import type { ChatCitation } from '@/features/sessions/api'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/utils'

export interface CitationsListProps {
    readonly citations: readonly ChatCitation[]
}

/**
 * 检索引用列表。
 *
 * 默认折叠：单条片段最长 4000 字，全部展开会把回答正文挤出视口。
 * `title` 允许为空，此时退回 `sourceId`，避免出现无法辨认的空行。
 */
export function CitationsList({ citations }: CitationsListProps) {
    const { t } = useTranslation()
    const [isExpanded, setIsExpanded] = useState(false)

    if (citations.length === 0) {
        return null
    }

    return (
        <section
            className="mt-3 rounded-[var(--cds-radius-card)] border border-border/60 bg-muted/30"
            aria-label={t('chat.citations.label')}
        >
            <Button
                variant="ghost"
                size="sm"
                className="w-full justify-start gap-1.5 px-2.5 text-xs text-muted-foreground hover:text-foreground"
                aria-expanded={isExpanded}
                onClick={() => setIsExpanded((value) => !value)}
            >
                <BookOpenText className="size-3.5" aria-hidden="true" />
                {t('chat.citations.title', { total: citations.length })}
                <ChevronDown
                    className={cn(
                        'ml-auto size-3.5 transition-transform',
                        isExpanded && 'rotate-180',
                    )}
                    aria-hidden="true"
                />
            </Button>

            {isExpanded ? (
                <ol className="flex flex-col gap-2 border-t border-border/60 px-3 py-2">
                    {citations.map((citation, index) => (
                        <li key={`${citation.sourceId}:${index}`} className="text-xs">
                            <div className="flex items-baseline justify-between gap-2">
                                <span className="break-words font-medium text-foreground">
                                    {index + 1}. {citation.title || citation.sourceId}
                                </span>
                                {typeof citation.score === 'number' ? (
                                    <span className="shrink-0 text-muted-foreground">
                                        {t('chat.citations.score', {
                                            percent: Math.round(citation.score * 100),
                                        })}
                                    </span>
                                ) : null}
                            </div>
                            <p className="mt-1 max-h-24 overflow-y-auto whitespace-pre-wrap break-words text-muted-foreground">
                                {citation.snippet}
                            </p>
                        </li>
                    ))}
                </ol>
            ) : null}
        </section>
    )
}
