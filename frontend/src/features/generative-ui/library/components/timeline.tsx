import {
  type ComponentRenderProps,
  defineComponent,
  type SubComponentOf,
} from '@openuidev/react-lang'
import { Steps as OpenUiSteps, StepsItem as OpenUiStepsItem } from '@openuidev/react-ui/Steps'
import { z } from 'zod'

/** 时间线条目：只声明数据，编号与连接线由官方 Steps 原语生成 */
export const TimelineItem = defineComponent({
  name: 'TimelineItem',
  description: '时间线条目：title 是节点标题，details 是节点说明',
  props: z.object({
    title: z.string().describe('节点标题'),
    details: z.string().describe('节点说明'),
  }),
  component: () => null,
})

type TimelineItemProps = { title: string; details: string }

type TimelineRenderProps = ComponentRenderProps<{ items: SubComponentOf<TimelineItemProps>[] }>

function TimelineRenderer({ props }: TimelineRenderProps) {
  const items = props.items ?? []
  if (items.length === 0) return null

  return (
    <OpenUiSteps>
      {items.map((item) => (
        <OpenUiStepsItem
          key={item.props.title}
          title={item.props.title}
          details={item.props.details}
        />
      ))}
    </OpenUiSteps>
  )
}

/** 时间线：官方 Steps 原语提供纵向节点与连接线，本项目只维护 Lang 契约 */
export const Timeline = defineComponent({
  name: 'Timeline',
  description: '时间线：按顺序展示带编号的节点与说明',
  props: z.object({
    items: z.array(TimelineItem.ref).describe('时间线条目列表，至少一项'),
  }),
  component: TimelineRenderer,
})
