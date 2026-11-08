import {
  type ComponentRenderProps,
  defineComponent,
  type SubComponentOf,
  useIsStreaming,
} from '@openuidev/react-lang'
import { CheckBoxGroup as OpenUiCheckBoxGroup } from '@openuidev/react-ui/CheckBoxGroup'
import { CheckBoxItem as OpenUiCheckBoxItem } from '@openuidev/react-ui/CheckBoxItem'
import { Label as OpenUiLabel } from '@openuidev/react-ui/Label'
import { z } from 'zod'

import { useFormField } from './use-form-field'

const EMPTY_SELECTION: readonly string[] = []

type CheckboxOptionProps = {
  value: string
  label: string
  description?: string
}

/** 复选选项只是语法占位，勾选状态由父级 CheckboxGroup 统一管理 */
export const CheckboxOption = defineComponent({
  name: 'CheckboxOption',
  description: '复选选项：value 是提交值，label 是展示文案',
  props: z.object({
    value: z.string().min(1).describe('选项值，选中时写入表单'),
    label: z.string().describe('选项展示文案'),
    description: z.string().optional().describe('选项下方的补充说明'),
  }),
  component: () => null,
})

type CheckboxGroupProps = {
  name: string
  label: string
  options: SubComponentOf<CheckboxOptionProps>[]
  defaultValues?: string[]
  description?: string
}

function parseSelection(raw: unknown): readonly string[] | undefined {
  if (Array.isArray(raw) && raw.every((item) => typeof item === 'string')) {
    return raw
  }

  return undefined
}

function CheckboxGroupRenderer({ props }: ComponentRenderProps<CheckboxGroupProps>) {
  const isStreaming = useIsStreaming()
  const field = useFormField<readonly string[]>({
    componentType: 'CheckboxGroup',
    name: props.name,
    ...(props.defaultValues === undefined ? {} : { defaultValue: props.defaultValues }),
    fallback: EMPTY_SELECTION,
    parse: parseSelection,
  })

  const options = (props.options ?? []).filter((option) => option.props.value !== '')
  if (options.length === 0) {
    return null
  }

  const toggle = (value: string, isChecked: boolean): void => {
    if (isChecked) {
      field.setValue(field.value.includes(value) ? field.value : [...field.value, value])
      return
    }

    field.setValue(field.value.filter((item) => item !== value))
  }

  return (
    <div className="flex flex-col gap-1.5">
      <OpenUiLabel>{props.label}</OpenUiLabel>
      {props.description ? <p className="text-xs text-muted-foreground">{props.description}</p> : null}
      <OpenUiCheckBoxGroup variant="card">
        {options.map((option) => (
          <OpenUiCheckBoxItem
            key={option.props.value}
            value={option.props.value}
            label={option.props.label}
            checked={field.value.includes(option.props.value)}
            disabled={isStreaming}
            onChange={(isChecked) => toggle(option.props.value, isChecked === true)}
            {...(option.props.description === undefined ? {} : { description: option.props.description })}
          />
        ))}
      </OpenUiCheckBoxGroup>
    </div>
  )
}

/** 多选组：选中值以字符串数组写入表单状态 */
export const CheckboxGroup = defineComponent({
  name: 'CheckboxGroup',
  description: '多选组：可同时选中多个选项，需要配合 CheckboxOption 使用',
  props: z.object({
    name: z.string().min(1).max(64).describe('字段名，提交时作为表单键'),
    label: z.string().describe('字段标题'),
    options: z.array(CheckboxOption.ref).min(1).describe('选项列表，至少一项'),
    defaultValues: z.array(z.string()).optional().describe('默认选中的选项值'),
    description: z.string().optional().describe('字段下方的补充说明'),
  }),
  component: CheckboxGroupRenderer,
})
