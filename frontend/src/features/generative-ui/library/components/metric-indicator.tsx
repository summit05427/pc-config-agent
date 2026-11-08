import { type ComponentRenderProps, defineComponent } from '@openuidev/react-lang'
import {
  MetricIndicatorInline as OpenUiMetricIndicatorInline,
  MetricIndicatorWithStrikethrough as OpenUiMetricIndicatorWithStrikethrough,
} from '@openuidev/react-ui/MetricIndicator'
import { z } from 'zod'

const trendSchema = z.object({
  direction: z.enum(['up', 'down']).describe('上升为 up，下降为 down'),
  value: z.number().describe('百分比数值，只传正数，符号由 direction 决定'),
})

type MetricIndicatorProps = {
  value: string
  subtext?: string
  previousValue?: string
  trend?: { direction: 'up' | 'down'; value: number }
  variant?: 'inline' | 'with-strikethrough'
}

function MetricIndicatorRenderer({ props }: ComponentRenderProps<MetricIndicatorProps>) {
  // 官方两个原语的 props 都是可选值；这里按需展开，避免把 undefined 显式传进组件
  const commonProps = {
    value: props.value,
    ...(props.subtext ? { subtext: props.subtext } : {}),
    ...(props.trend ? { trend: props.trend } : {}),
  }

  if (props.variant === 'inline') {
    return <OpenUiMetricIndicatorInline {...commonProps} />
  }

  return (
    <OpenUiMetricIndicatorWithStrikethrough
      {...commonProps}
      {...(props.previousValue ? { previousValue: props.previousValue } : {})}
    />
  )
}

/** 关键指标：官方原语提供排版，本项目只维护 Lang 契约与默认形态 */
export const MetricIndicator = defineComponent({
  name: 'MetricIndicator',
  description: '关键指标：突出显示单个数值，可带环比趋势、副标题与划线对比值',
  props: z.object({
    value: z.string().describe('主数值，已格式化，例如 ¥1,234 或 42%'),
    subtext: z.string().optional().describe('数值下方的说明文案'),
    previousValue: z.string().optional().describe('被划掉的历史值，仅 with-strikethrough 形态使用'),
    trend: trendSchema.optional().describe('环比变化'),
    variant: z
      .enum(['inline', 'with-strikethrough'])
      .optional()
      .describe('inline 单行展示；with-strikethrough 展示划线历史值，默认值'),
  }),
  component: MetricIndicatorRenderer,
})
