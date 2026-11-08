import {
  type ComponentRenderProps,
  defineComponent,
  type SubComponentOf,
} from '@openuidev/react-lang'
import {
  MetricIndicatorInline as OpenUiMetricIndicatorInline,
  MetricIndicatorWithStrikethrough as OpenUiMetricIndicatorWithStrikethrough,
} from '@openuidev/react-ui/MetricIndicator'
import { z } from 'zod'

const trendSchema = z.object({
  direction: z.enum(['up', 'down']).describe('上升为 up，下降为 down'),
  value: z.number().describe('百分比数值，只传正数'),
})

/** 指标组里的单个指标：只声明数据，渲染由父级 StatGroup 统一完成 */
export const StatItem = defineComponent({
  name: 'StatItem',
  description: '单个指标：value 是主数值，可带副标题、环比趋势与划线对比值',
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
  component: () => null,
})

type StatItemProps = {
  value: string
  subtext?: string
  previousValue?: string
  trend?: { direction: 'up' | 'down'; value: number }
  variant?: 'inline' | 'with-strikethrough'
}

function StatItemView({ item }: { item: StatItemProps }) {
  const commonProps = {
    value: item.value,
    ...(item.subtext ? { subtext: item.subtext } : {}),
    ...(item.trend ? { trend: item.trend } : {}),
  }

  if (item.variant === 'inline') {
    return <OpenUiMetricIndicatorInline {...commonProps} />
  }

  return (
    <OpenUiMetricIndicatorWithStrikethrough
      {...commonProps}
      {...(item.previousValue ? { previousValue: item.previousValue } : {})}
    />
  )
}

type StatGroupRenderProps = ComponentRenderProps<{ items: SubComponentOf<StatItemProps>[] }>

function StatGroupRenderer({ props }: StatGroupRenderProps) {
  const items = props.items ?? []
  if (items.length === 0) return null

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {items.map((item) => (
        <StatItemView key={item.props.value} item={item.props} />
      ))}
    </div>
  )
}

/** 指标组：官方没有对应容器原语，自研栅格；指标本体复用官方 MetricIndicator */
export const StatGroup = defineComponent({
  name: 'StatGroup',
  description: '指标组：并排展示多个关键指标',
  props: z.object({
    items: z.array(StatItem.ref).describe('指标列表，至少一项'),
  }),
  component: StatGroupRenderer,
})
