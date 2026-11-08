import {
  type ComponentRenderProps,
  defineComponent,
  type SubComponentOf,
} from '@openuidev/react-lang'
import {
  Tabs as OpenUiTabs,
  TabsContent as OpenUiTabsContent,
  TabsList as OpenUiTabsList,
  TabsTrigger as OpenUiTabsTrigger,
} from '@openuidev/react-ui/Tabs'
import { z } from 'zod'

/**
 * 标签页项的 Lang 契约。
 *
 * 只声明数据、不渲染：真正的 DOM 由父级 Tabs 统一生成，
 * 这样 Radix 的 value 与子节点顺序才能保持一一对应。
 */
export const TabItem = defineComponent({
  name: 'TabItem',
  description: '标签页项：value 是唯一标识，trigger 是标签文案，content 是标签页内的子组件列表',
  props: z.object({
    value: z.string().describe('标签页唯一标识，同一 Tabs 内不可重复'),
    trigger: z.string().describe('标签文案'),
    content: z.array(z.unknown()).describe('标签页内容'),
  }),
  component: () => null,
})

type TabItemProps = { value: string; trigger: string; content: unknown[] }

type TabsRenderProps = ComponentRenderProps<{ items: SubComponentOf<TabItemProps>[] }>

function TabsRenderer({ props, renderNode }: TabsRenderProps) {
  const items = (props.items ?? []).filter((item) => item.props.value.length > 0)
  if (items.length === 0) return null

  return (
    <OpenUiTabs defaultValue={items[0]?.props.value}>
      <OpenUiTabsList>
        {items.map((item) => (
          <OpenUiTabsTrigger
            key={item.props.value}
            value={item.props.value}
            text={item.props.trigger}
          />
        ))}
      </OpenUiTabsList>
      {items.map((item) => (
        <OpenUiTabsContent key={item.props.value} value={item.props.value}>
          {renderNode(item.props.content)}
        </OpenUiTabsContent>
      ))}
    </OpenUiTabs>
  )
}

/** 标签页容器：官方原语负责交互与样式，本项目只维护 Lang 契约 */
export const Tabs = defineComponent({
  name: 'Tabs',
  description: '标签页容器：在同一区域切换多组内容',
  props: z.object({
    items: z.array(TabItem.ref).describe('标签页列表，至少一项'),
  }),
  component: TabsRenderer,
})
