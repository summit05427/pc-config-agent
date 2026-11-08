import {
  type ComponentRenderProps,
  defineComponent,
  type SubComponentOf,
  useIsStreaming,
} from '@openuidev/react-lang'
import { Label as OpenUiLabel } from '@openuidev/react-ui/Label'
import {
  Select as OpenUiSelect,
  SelectContent as OpenUiSelectContent,
  SelectItem as OpenUiSelectItem,
  SelectTrigger as OpenUiSelectTrigger,
  SelectValue as OpenUiSelectValue,
} from '@openuidev/react-ui/Select'
import { useId } from 'react'
import { z } from 'zod'

import { useFormField } from './use-form-field'

type SelectOptionProps = {
  value: string
  label: string
}

/** 选项只是语法占位，实际渲染由父级 Select 统一处理 */
export const SelectOption = defineComponent({
  name: 'SelectOption',
  description: '下拉选项：value 是提交值，label 是展示文案',
  props: z.object({
    value: z.string().min(1).describe('选项值，提交时写入表单'),
    label: z.string().describe('选项展示文案'),
  }),
  component: () => null,
})

type SelectProps = {
  name: string
  label: string
  options: SubComponentOf<SelectOptionProps>[]
  placeholder?: string
  defaultValue?: string
  description?: string
}

function SelectRenderer({ props }: ComponentRenderProps<SelectProps>) {
  const isStreaming = useIsStreaming()
  const fieldId = useId()
  const field = useFormField({
    componentType: 'Select',
    name: props.name,
    ...(props.defaultValue === undefined ? {} : { defaultValue: props.defaultValue }),
    fallback: '',
    parse: (raw) => (typeof raw === 'string' && raw !== '' ? raw : undefined),
  })

  // Radix Select 不接受空字符串选项值，这类选项直接跳过
  const options = (props.options ?? []).filter((option) => option.props.value !== '')
  if (options.length === 0) {
    return null
  }

  return (
    <div className="flex flex-col gap-1.5">
      <OpenUiLabel htmlFor={fieldId}>{props.label}</OpenUiLabel>
      {props.description ? <p className="text-xs text-muted-foreground">{props.description}</p> : null}
      <OpenUiSelect
        value={field.value}
        onValueChange={field.setValue}
        disabled={isStreaming}
        size="md"
      >
        <OpenUiSelectTrigger id={fieldId} size="md">
          <OpenUiSelectValue placeholder={props.placeholder ?? '请选择'} />
        </OpenUiSelectTrigger>
        <OpenUiSelectContent>
          {options.map((option) => (
            <OpenUiSelectItem key={option.props.value} value={option.props.value}>
              {option.props.label}
            </OpenUiSelectItem>
          ))}
        </OpenUiSelectContent>
      </OpenUiSelect>
    </div>
  )
}

/** 单选下拉：选中值写入表单状态 */
export const Select = defineComponent({
  name: 'Select',
  description: '下拉选择框：从多个选项中选择一个，需要配合 SelectOption 使用',
  props: z.object({
    name: z.string().min(1).max(64).describe('字段名，提交时作为表单键'),
    label: z.string().describe('字段标题'),
    options: z.array(SelectOption.ref).min(1).describe('下拉选项列表，至少一项'),
    placeholder: z.string().optional().describe('未选择时的提示，默认「请选择」'),
    defaultValue: z.string().optional().describe('默认选中的选项值'),
    description: z.string().optional().describe('字段下方的补充说明'),
  }),
  component: SelectRenderer,
})
