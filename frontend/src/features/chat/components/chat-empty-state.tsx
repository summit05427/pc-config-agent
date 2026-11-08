import { useTranslation } from 'react-i18next'

import { BrandMark } from '@/shared/ui/brand-mark'

/**
 * 空会话态。
 *
 * 只解释 Agent 如何工作，不编造示例任务；输入焦点仍由底部输入框承担。
 */
export function ChatEmptyState() {
    const { t } = useTranslation()

    return (
        <div className="flex flex-1 items-center justify-center py-16">
            <div className="max-w-md text-center">
                {/* BrandMark 内是块级图片，text-center 对块级元素无效，需用 flex 居中 */}
                <div className="flex justify-center">
                    <BrandMark />
                </div>
                {/* 空会话标题属于展示型文案，走衬线；说明文字仍是 UI 文案，保留无衬线 */}
                <h2 className="mt-4 font-serif text-2xl font-normal text-foreground">
                    {t('chat.empty.title')}
                </h2>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {t('chat.empty.description')}
                </p>
            </div>
        </div>
    )
}
