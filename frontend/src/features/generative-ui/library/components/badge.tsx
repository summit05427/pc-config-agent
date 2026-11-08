import { defineComponent } from '@openuidev/react-lang'
import { Tag } from '@openuidev/react-ui/Tag'
import { z } from 'zod'

type BadgeTone = 'neutral' | 'success' | 'warning' | 'danger'

/**
 * 语气到官方 Tag 变体的映射。
 *
 * 官方 Tag 用 variant 控制配色、size 控制高度；这里固定 sm 以匹配行内标签的视觉，
 * 不在适配层复制颜色值，配色仍由官方样式表与 --openui-* 变量决定。
 */
const TONE_VARIANTS: Record<BadgeTone, 'neutral' | 'success' | 'warning' | 'danger'> = {
  neutral: 'neutral',
  success: 'success',
  warning: 'warning',
  danger: 'danger',
}

/** 状态徽标；颜色只使用设计 Token，不硬编码色值 */
export const Badge = defineComponent({
  name: 'Badge',
  description: '展示简短状态或标签，支持中性、成功、警告、危险四种语气',
  props: z.object({
    label: z.string().describe('徽标文案'),
    tone: z.enum(['neutral', 'success', 'warning', 'danger']).optional().describe('语气，默认中性'),
  }),
  component: ({ props }) => (
    // w-fit 避免 Tag 作为 flex 子项被拉满整行
    <Tag
      size="sm"
      variant={TONE_VARIANTS[props.tone ?? 'neutral']}
      text={props.label}
      className="w-fit"
    />
  ),
})
