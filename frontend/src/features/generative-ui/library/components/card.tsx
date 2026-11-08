import { defineComponent } from '@openuidev/react-lang'
import { Card as OpenUiCard } from '@openuidev/react-ui/Card'
import { CardHeader } from '@openuidev/react-ui/CardHeader'
import { z } from 'zod'

import { cn } from '@/shared/lib/utils'

/** 带可选标题与说明的内容卡片 */
export const Card = defineComponent({
  name: 'Card',
  description: '内容卡片，包含可选标题、说明与子组件列表',
  props: z.object({
    children: z.array(z.unknown()).describe('卡片内容'),
    title: z.string().optional().describe('卡片标题'),
    description: z.string().optional().describe('标题下方的补充说明'),
  }),
  component: ({ props, renderNode }) => {
    const hasHeader = Boolean(props.title || props.description)

    return (
      // 官方 clear 变体只负责结构与纵向排列，表面样式通过 className 对齐 CDS Token
      <OpenUiCard
        variant="clear"
        width="full"
        className={cn(
          'gap-3 rounded-lg border border-border bg-card px-4',
          hasHeader ? 'py-4' : 'py-0',
        )}
      >
        {hasHeader ? (
          <CardHeader title={props.title} subtitle={props.description} className="gap-1" />
        ) : null}
        {renderNode(props.children)}
      </OpenUiCard>
    )
  },
})
