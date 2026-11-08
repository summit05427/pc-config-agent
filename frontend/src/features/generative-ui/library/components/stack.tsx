import { defineComponent } from '@openuidev/react-lang'
import { z } from 'zod'

import { cn } from '@/shared/lib/utils'

const DIRECTION_CLASSES = {
  vertical: 'flex-col',
  horizontal: 'flex-row',
} as const

const GAP_CLASSES = {
  sm: 'gap-2',
  md: 'gap-4',
  lg: 'gap-6',
} as const

const ALIGN_CLASSES = {
  start: 'items-start',
  center: 'items-center',
  end: 'items-end',
  stretch: 'items-stretch',
} as const

/** 生成式 UI 的根布局组件；模型输出的 root 必须调用它 */
export const Stack = defineComponent({
  name: 'Stack',
  description: '纵向或横向排列子组件的布局容器，可作为界面根节点',
  props: z.object({
    children: z.array(z.unknown()).describe('子组件列表'),
    direction: z.enum(['vertical', 'horizontal']).optional().describe('排列方向，默认纵向'),
    gap: z.enum(['sm', 'md', 'lg']).optional().describe('子组件间距，默认 md'),
    align: z
      .enum(['start', 'center', 'end', 'stretch'])
      .optional()
      .describe('交叉轴对齐方式，默认 stretch'),
  }),
  component: ({ props, renderNode }) => (
    <div
      className={cn(
        'flex min-w-0',
        DIRECTION_CLASSES[props.direction ?? 'vertical'],
        GAP_CLASSES[props.gap ?? 'md'],
        ALIGN_CLASSES[props.align ?? 'stretch'],
      )}
    >
      {renderNode(props.children)}
    </div>
  ),
})
