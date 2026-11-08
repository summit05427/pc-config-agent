import { defineComponent } from '@openuidev/react-lang'
import { TextContent } from '@openuidev/react-ui/TextContent'
import { z } from 'zod'

import { cn } from '@/shared/lib/utils'

type TextVariant = 'body' | 'heading' | 'muted' | 'caption'

/**
 * 语义样式到排版工具类的映射。
 *
 * 官方 TextContent 只提供文本表面与默认字色，字号字重由这里透传的 className 决定，
 * 因此排版仍然落在设计 Token 上，不出现硬编码字号。
 */
const TEXT_VARIANTS: Record<TextVariant, string> = {
  body: 'text-sm leading-6 text-foreground',
  heading: 'text-base font-semibold tracking-[-0.01em] text-foreground',
  muted: 'text-sm leading-6 text-muted-foreground',
  caption: 'text-xs leading-5 text-muted-foreground',
}

/** 纯文本组件；只做纯文本渲染，不在界面块内解析富文本 */
export const Text = defineComponent({
  name: 'Text',
  description: '展示一段纯文本，支持正文、标题、弱化与说明四种样式',
  props: z.object({
    content: z.string().describe('要展示的文本'),
    variant: z
      .enum(['body', 'heading', 'muted', 'caption'])
      .optional()
      .describe('文本样式，默认 body'),
  }),
  component: ({ props }) => {
    const variant = props.variant ?? 'body'

    return (
      // clear 变体去掉表面背景，border-0 / p-0 清掉官方容器的边框与内边距
      <TextContent variant="clear" className={cn('min-w-0 border-0 p-0', TEXT_VARIANTS[variant])}>
        {/* 标题保留 h3 语义，其余变体直接作为文本节点 */}
        {variant === 'heading' ? <h3>{props.content}</h3> : props.content}
      </TextContent>
    )
  },
})
