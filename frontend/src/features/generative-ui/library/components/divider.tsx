import { defineComponent } from '@openuidev/react-lang'
import { Separator } from '@openuidev/react-ui/Separator'
import { z } from 'zod'

/** 内容分隔线；不接收任何属性，避免模型用样式属性绕开设计系统 */
export const Divider = defineComponent({
  name: 'Divider',
  description: '一条水平分隔线，用于在卡片内分隔内容',
  props: z.object({}),
  // 官方 Separator 基于 Radix，方向与无障碍语义由原语提供，这里只补垂直间距
  component: () => <Separator className="my-1" />,
})
