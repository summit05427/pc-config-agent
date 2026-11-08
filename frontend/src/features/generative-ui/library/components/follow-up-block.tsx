import {
  type ComponentRenderProps,
  defineComponent,
  useIsStreaming,
  useTriggerAction,
  type SubComponentOf,
} from '@openuidev/react-lang'
import { FollowUpItem as OpenUiFollowUpItem } from '@openuidev/react-ui/FollowUpItem'
import { z } from 'zod'

/** 追问项：点击后把文案作为用户消息继续对话 */
export const FollowUpItem = defineComponent({
  name: 'FollowUpItem',
  description: '单条追问建议：点击后以该文案继续对话',
  props: z.object({
    text: z.string().describe('建议文案，点击后原样发送'),
  }),
  component: () => null,
})

type FollowUpItemProps = { text: string }

type FollowUpBlockRenderProps = ComponentRenderProps<{ items: SubComponentOf<FollowUpItemProps>[] }>

function FollowUpBlockRenderer({ props }: FollowUpBlockRenderProps) {
  const isStreaming = useIsStreaming()
  const triggerAction = useTriggerAction()
  const items = (props.items ?? []).filter((item) => item.props.text.length > 0)
  if (items.length === 0) return null

  // 官方 FollowUpBlock 的表头写死为英文 "Related Queries"，
  // 这里复用它提供的 Item 原语，容器与中文标题由本项目维护
  return (
    <div className="flex flex-col gap-2">
      <span className="text-xs font-medium text-muted-foreground">你可能还想问</span>
      {items.map((item) => (
        <OpenUiFollowUpItem
          key={item.props.text}
          text={item.props.text}
          disabled={isStreaming}
          onClick={() => {
            void triggerAction(item.props.text)
          }}
        />
      ))}
    </div>
  )
}

/** 追问建议列表：官方 Item 原语 + 本项目容器 */
export const FollowUpBlock = defineComponent({
  name: 'FollowUpBlock',
  description: '追问建议：列出一条或多条可点击的后续问题，放在回答末尾',
  props: z.object({
    items: z.array(FollowUpItem.ref).describe('追问建议列表，至少一条'),
  }),
  component: FollowUpBlockRenderer,
})
