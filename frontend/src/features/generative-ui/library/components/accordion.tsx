import {
  type ComponentRenderProps,
  defineComponent,
  type SubComponentOf,
} from '@openuidev/react-lang'
import {
  Accordion as OpenUiAccordion,
  AccordionContent as OpenUiAccordionContent,
  AccordionItem as OpenUiAccordionItem,
  AccordionTrigger as OpenUiAccordionTrigger,
} from '@openuidev/react-ui/Accordion'
import { z } from 'zod'

/** 折叠面板项：只声明数据，渲染由父级 Accordion 统一完成 */
export const AccordionItem = defineComponent({
  name: 'AccordionItem',
  description: '折叠项：value 是唯一标识，trigger 是标题，content 是展开后的子组件列表',
  props: z.object({
    value: z.string().describe('折叠项唯一标识，同一 Accordion 内不可重复'),
    trigger: z.string().describe('折叠标题'),
    content: z.array(z.unknown()).describe('展开后的内容'),
  }),
  component: () => null,
})

type AccordionItemProps = { value: string; trigger: string; content: unknown[] }

type AccordionRenderProps = ComponentRenderProps<{ items: SubComponentOf<AccordionItemProps>[] }>

function AccordionRenderer({ props, renderNode }: AccordionRenderProps) {
  const items = (props.items ?? []).filter((item) => item.props.value.length > 0)
  const firstItem = items[0]
  if (!firstItem) return null

  return (
    <OpenUiAccordion type="single" collapsible defaultValue={firstItem.props.value}>
      {items.map((item) => (
        <OpenUiAccordionItem key={item.props.value} value={item.props.value}>
          <OpenUiAccordionTrigger text={item.props.trigger} />
          <OpenUiAccordionContent>{renderNode(item.props.content)}</OpenUiAccordionContent>
        </OpenUiAccordionItem>
      ))}
    </OpenUiAccordion>
  )
}

/** 折叠面板：官方原语负责交互与样式，本项目只维护 Lang 契约 */
export const Accordion = defineComponent({
  name: 'Accordion',
  description: '折叠面板：把多段内容收进可展开的标题下',
  props: z.object({
    items: z.array(AccordionItem.ref).describe('折叠项列表，至少一项'),
  }),
  component: AccordionRenderer,
})
