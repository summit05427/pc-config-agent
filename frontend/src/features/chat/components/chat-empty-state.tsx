import { useTranslation } from 'react-i18next'

import { BrandMark } from '@/shared/ui/brand-mark'
import { Button } from '@/shared/ui/button'

/** 示例引导固定四条：预算、用途、分辨率、品牌偏好各给一个可点击起点 */
const EXAMPLE_KEYS = ['example1', 'example2', 'example3', 'example4'] as const

export interface ChatEmptyStateProps {
    /** 点击示例直接发送；未提供时示例仅作为静态引导 */
    readonly onSelectExample?: (prompt: string) => void
}

/**
 * 空会话态。
 *
 * 入口收敛为单一的 PC 配置推荐，不再展示通用模板示例；
 * 输入焦点仍由底部输入框承担，示例按钮只是可选快捷入口。
 */
export function ChatEmptyState({ onSelectExample }: ChatEmptyStateProps) {
    const { t } = useTranslation()

    return (
        <div className="flex flex-1 items-center justify-center py-16">
            <div className="max-w-lg text-center">
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

                <div className="mt-6 flex flex-wrap justify-center gap-2">
                    {EXAMPLE_KEYS.map((key) => {
                        const prompt = t(`chat.empty.${key}`)
                        return (
                            <Button
                                key={key}
                                type="button"
                                variant="outline"
                                size="sm"
                                className="h-auto max-w-full whitespace-normal text-left text-xs"
                                onClick={() => onSelectExample?.(prompt)}
                            >
                                {prompt}
                            </Button>
                        )
                    })}
                </div>
            </div>
        </div>
    )
}
