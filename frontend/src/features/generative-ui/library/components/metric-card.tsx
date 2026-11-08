import { defineComponent } from '@openuidev/react-lang'
import { Card as OpenUiCard } from '@openuidev/react-ui/Card'
import { MetricIndicatorInline } from '@openuidev/react-ui/MetricIndicator'
import { TextContent } from '@openuidev/react-ui/TextContent'
import { z } from 'zod'

import { cn } from '@/shared/lib/utils'

/** 变化方向只影响文案颜色，语义与配色都复用设计 Token */
const TREND_CLASSES = {
  up: 'text-success',
  down: 'text-destructive',
  flat: 'text-muted-foreground',
} as const

/** 单指标展示卡；数值由模型预先格式化，前端不做本地化换算 */
export const MetricCard = defineComponent({
  name: 'MetricCard',
  description: '展示单个指标的名称、数值与可选变化量',
  props: z.object({
    label: z.string().describe('指标名称'),
    value: z.string().describe('已格式化的指标值'),
    delta: z.string().optional().describe('变化量，例如 +8.2%'),
    trend: z.enum(['up', 'down', 'flat']).optional().describe('变化方向，决定变化量颜色'),
    hint: z.string().optional().describe('补充说明'),
  }),
  component: ({ props }) => (
    // 官方没有独立指标卡原语，这里由 Card + MetricIndicator + TextContent 组合而成
    <OpenUiCard
      variant="clear"
      width="full"
      className="gap-1 rounded-lg border border-border bg-card px-4 py-4"
    >
      <TextContent variant="clear" className="border-0 p-0 text-xs text-muted-foreground">
        {props.label}
      </TextContent>
      <MetricIndicatorInline value={props.value} />
      {props.delta ? (
        <TextContent
          variant="clear"
          className={cn(
            'border-0 p-0 text-xs font-medium tabular-nums',
            TREND_CLASSES[props.trend ?? 'flat'],
          )}
        >
          {props.delta}
        </TextContent>
      ) : null}
      {props.hint ? (
        <TextContent variant="clear" className="border-0 p-0 text-xs text-muted-foreground">
          {props.hint}
        </TextContent>
      ) : null}
    </OpenUiCard>
  ),
})
