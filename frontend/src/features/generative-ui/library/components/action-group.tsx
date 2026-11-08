import {
  type ComponentRenderProps,
  defineComponent,
  type SubComponentOf,
} from '@openuidev/react-lang'
import type { ButtonProps } from '@openuidev/react-ui/Button'
import { Buttons } from '@openuidev/react-ui/Buttons'
import type { ReactElement } from 'react'
import { z } from 'zod'

import { Button } from './button'

type ActionGroupProps = {
  buttons: SubComponentOf<{ label: string; confirm?: boolean }>[]
  variant?: 'horizontal' | 'vertical'
}

function ActionGroupRenderer({ props, renderNode }: ComponentRenderProps<ActionGroupProps>) {
  const buttons = props.buttons ?? []
  if (buttons.length === 0) {
    return null
  }

  return (
    <Buttons variant={props.variant ?? 'horizontal'} className="w-full">
      {/*
        官方 Buttons 的 children 只接受 Button 元素，而 renderNode 返回 ReactNode。
        元素类型由 Lang 契约保证（buttons 只允许 Button.ref），因此这里只做类型收窄。
      */}
      {renderNode(buttons) as ReactElement<ButtonProps>}
    </Buttons>
  )
}

/** 按钮组：只做横向/纵向布局，按钮本身仍是本地 Button */
export const ActionGroup = defineComponent({
  name: 'ActionGroup',
  description: '按钮组：把多个操作按钮横向或纵向排列',
  props: z.object({
    buttons: z.array(Button.ref).describe('按钮列表，至少一个 Button'),
    variant: z.enum(['horizontal', 'vertical']).optional().describe('排列方向，默认 horizontal'),
  }),
  component: ActionGroupRenderer,
})
