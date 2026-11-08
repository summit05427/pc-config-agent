import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Brain, ChevronRight } from 'lucide-react'

import { cn } from '@/shared/lib/utils'

export interface ReasoningPanelProps {
    /** 已累积的思考文本；空串时不渲染，避免每轮都出现空面板 */
    readonly text: string
    /** 消息仍在生成：默认展开，结束后自动收起 */
    readonly live?: boolean
}

/**
 * 模型思考过程。
 *
 * 默认展开规则在渲染期推导：流式期间展开、结束后收起；用户手动切换后
 * 以其选择为准，避免每帧重置。思考内容按纯文本渲染，不参与 Markdown 解析。
 */
export function ReasoningPanel({ text, live = false }: ReasoningPanelProps) {
    const { t } = useTranslation()
    const [userOpen, setUserOpen] = useState<boolean | null>(null)

    if (!text.trim()) {
        return null
    }

    const isOpen = userOpen ?? live

    return (
        <div className="mb-2">
            <button
                type="button"
                className="inline-flex h-7 items-center gap-1.5 rounded-md px-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                aria-expanded={isOpen}
                onClick={() => setUserOpen(!isOpen)}
            >
                <Brain className={cn('size-3.5', live && 'text-clay')} />
                <span className="font-medium">{t('chat.reasoning.title')}</span>
                {live ? (
                    <span className="text-muted-foreground">{t('chat.reasoning.inProgress')}</span>
                ) : null}
                <ChevronRight
                    className={cn('size-3.5 transition-transform', isOpen && 'rotate-90')}
                    aria-hidden="true"
                />
            </button>

            {isOpen ? (
                <div className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap break-words border-l border-border pl-3 text-xs leading-relaxed text-muted-foreground">
                    {text}
                </div>
            ) : null}
        </div>
    )
}
