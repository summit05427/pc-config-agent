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
 * 用两行网格：标题块跨两行，视觉中心落在整个对话区（而不是被底部推荐块
 * 挤到上半区）；「为你推荐」固定在第二行，紧贴输入框上方并与输入框同宽，
 * 左缘自然对齐。窗口过矮时网格按内容撑高并由外层滚动，不会出现叠压。
 */
export function ChatEmptyState({ onSelectExample }: ChatEmptyStateProps) {
  const { t } = useTranslation()

  return (
    <div className="grid flex-1 grid-rows-[1fr_auto] pt-6">
      {/* 标题块占据第一行并在其中垂直居中，第二行留给推荐列表，任何高度都不会与列表叠压 */}
      <div className="col-start-1 row-start-1 flex flex-col items-center justify-center pb-6">
        <BrandMark />
        <h2 className="mt-4 max-w-2xl text-center font-serif text-display text-foreground">
          {t('chat.empty.title')}
        </h2>
        <p className="mt-3 max-w-md text-center text-sm leading-relaxed text-muted-foreground">
          {t('chat.empty.description')}
        </p>
      </div>

      <section
        className="col-start-1 row-start-2 mx-auto w-full max-w-[var(--app-content-width)] pb-2"
        aria-labelledby="chat-recommend-heading"
      >
        <h3 id="chat-recommend-heading" className="text-xs font-normal text-muted-foreground">
          {t('chat.empty.recommendTitle')}
        </h3>
        <div className="mt-2.5 flex flex-col items-start gap-2">
          {EXAMPLE_KEYS.map((key) => {
            const prompt = t(`chat.empty.${key}`)
            return (
              <Button
                key={key}
                type="button"
                variant="outline"
                className="h-auto min-h-[var(--control-height-md)] max-w-full justify-start whitespace-normal px-3 py-1.5 text-left font-normal"
                onClick={() => onSelectExample?.(prompt)}
              >
                {prompt}
              </Button>
            )
          })}
        </div>
      </section>
    </div>
  )
}
