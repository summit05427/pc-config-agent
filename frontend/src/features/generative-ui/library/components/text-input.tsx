import { type ComponentRenderProps, defineComponent, useIsStreaming } from '@openuidev/react-lang'
import { Input as OpenUiInput } from '@openuidev/react-ui/Input'
import { Label as OpenUiLabel } from '@openuidev/react-ui/Label'
import { useId } from 'react'
import { z } from 'zod'

import { useFormField } from './use-form-field'

type TextInputProps = {
  name: string
  label: string
  placeholder?: string
  defaultValue?: string
  description?: string
}

function TextInputRenderer({ props }: ComponentRenderProps<TextInputProps>) {
  const isStreaming = useIsStreaming()
  const fieldId = useId()
  const field = useFormField({
    componentType: 'TextInput',
    name: props.name,
    ...(props.defaultValue === undefined ? {} : { defaultValue: props.defaultValue }),
    fallback: '',
    parse: (raw) => (typeof raw === 'string' ? raw : undefined),
  })

  return (
    <div className="flex flex-col gap-1.5">
      <OpenUiLabel htmlFor={fieldId}>{props.label}</OpenUiLabel>
      {props.description ? <p className="text-xs text-muted-foreground">{props.description}</p> : null}
      <OpenUiInput
        id={fieldId}
        size="medium"
        type="text"
        value={field.value}
        disabled={isStreaming}
        {...(props.placeholder === undefined ? {} : { placeholder: props.placeholder })}
        onChange={(event) => field.setValue(event.target.value)}
      />
    </div>
  )
}

/** 单行文本输入：值写入 OpenUI 表单状态，Form 提交时随按钮一起回传 */
export const TextInput = defineComponent({
  name: 'TextInput',
  description: '单行文本输入框，用于姓名、邮箱、备注等短文本',
  props: z.object({
    name: z.string().min(1).max(64).describe('字段名，提交时作为表单键'),
    label: z.string().describe('字段标题'),
    placeholder: z.string().optional().describe('输入提示'),
    defaultValue: z.string().optional().describe('默认值'),
    description: z.string().optional().describe('字段下方的补充说明'),
  }),
  component: TextInputRenderer,
})
