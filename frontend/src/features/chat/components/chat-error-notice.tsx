import { useTranslation } from 'react-i18next'

export interface ChatErrorNoticeProps {
    readonly message: string
    readonly onRetry: () => void
}

/**
 * 对话错误条。
 *
 * 使用 role="alert" 让辅助技术立即播报；已生成内容仍保留在上方，
 * 因此这里只提供重试，不做清空式「重新开始」。
 */
export function ChatErrorNotice({ message, onRetry }: ChatErrorNoticeProps) {
    const { t } = useTranslation()

    return (
        <div
            className="mb-2 flex items-start gap-2 rounded-[var(--cds-radius-btn-md)] border border-destructive/25 bg-destructive/10 px-3 py-2 text-xs text-destructive"
            role="alert"
        >
            <p className="min-w-0 flex-1 leading-relaxed">{message}</p>
            <button
                type="button"
                className="shrink-0 rounded px-1 text-destructive/80 hover:text-destructive"
                onClick={onRetry}
            >
                {t('common.retry')}
            </button>
        </div>
    )
}
