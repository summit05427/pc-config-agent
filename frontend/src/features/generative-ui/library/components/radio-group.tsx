import {
  type ComponentRenderProps,
  defineComponent,
  type SubComponentOf,
  useIsStreaming,
} from '@openuidev/react-lang'
import { Label as OpenUiLabel } from '@openuidev/react-ui/Label'
import { RadioGroup as OpenUiRadioGroup } from '@openuidev/react-ui/RadioGroup'
import { RadioItem as OpenUiRadioItem } from '@openuidev/react-ui/RadioItem'
import { z } from 'zod'

import { useFormField } from './use-form-field'

type RadioOptionProps = {
  value: string
  label: string
  description?: string
}

/** 单选选项只是语法占位，选中状态由父级 RadioGroup 统一管理 */
export const RadioOption = defineComponent({
  name: 'RadioOption',
  description: '单选选项：value 是提交值，label 是展示文案',
  props: z.object({
    value: z.string().min(1).describe('选项值，选中时写入表单'),
    label: z.string().describe('选项展示文案'),
    description: z.string().optional().describe('选项下方的补充说明'),
  }),
  component: () => null,
})

type RadioGroupProps = {
  name: string
  label: string
  options: SubComponentOf<RadioOptionProps>[]
  defaultValue?: string
  description?: string
}

function RadioGroupRenderer({ props }: ComponentRenderProps<RadioGroupProps>) {
  const isStreaming = useIsStreaming()
  const field = useFormField({
    componentType: 'RadioGroup',
    name: props.name,
    ...(props.defaultValue === undefined ? {} : { defaultValue: props.defaultValue }),
    fallback: '',
    parse: (raw) => (typeof raw === 'string' && raw !== '' ? raw : undefined),
  })

  const options = (props.options ?? []).filter((option) => option.props.value !== '')
  if (options.length === 0) {
    return null
  }

  return (
    <div className="flex flex-col gap-1.5">
      <OpenUiLabel>{props.label}</OpenUiLabel>
      {props.description ? <p className="text-xs text-muted-foreground">{props.description}</p> : null}
      <OpenUiRadioGroup
        variant="card"
        value={field.value}
        onValueChange={field.setValue}
        disabled={isStreaming}
      >
        {options.map((option) => (
          <OpenUiRadioItem
            key={option.props.value}
            value={option.props.value}
            label={option.props.label}
            {...(option.props.description === undefined ? {} : { description: option.props.description })}
          />
        ))}
      </OpenUiRadioGroup>
    </div>
  )
}

/** 单选组：选中值以字符串写入表单状态 */
export const RadioGroup = defineComponent({
  name: 'RadioGroup',
  description: '单选组：只能选中一个选项，需要配合 RadioOption 使用',
  props: z.object({
    name: z.string().min(1).max(64).describe('字段名，提交时作为表单键'),
    label: z.string().describe('字段标题'),
    options: z.array(RadioOption.ref).min(1).describe('选项列表，至少一项'),
    defaultValue: z.string().optional().describe('默认选中的选项值'),
    description: z.string().optional().describe('字段下方的补充说明'),
  }),
  component: RadioGroupRenderer,
})
