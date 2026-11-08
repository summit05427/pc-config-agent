import { type ComponentRenderProps, defineComponent, useIsStreaming } from '@openuidev/react-lang'
import { Input as OpenUiInput } from '@openuidev/react-ui/Input'
import { Label as OpenUiLabel } from '@openuidev/react-ui/Label'
import { useId } from 'react'
import { z } from 'zod'

import { useFormField } from './use-form-field'

/** 空字符串表示「用户清空了输入」，与 0 区分，提交时也不会被当成有效数值 */
type NumberFieldValue = number | ''

type NumberInputProps = {
  name: string
  label: string
  placeholder?: string
  defaultValue?: number
  min?: number
  max?: number
  step?: number
  description?: string
}

function parseNumberField(raw: unknown): NumberFieldValue | undefined {
  if (typeof raw === 'number' && Number.isFinite(raw)) {
    return raw
  }

  if (raw === '') {
    return ''
  }

  if (typeof raw === 'string') {
    const parsed = Number(raw)
    return Number.isFinite(parsed) ? parsed : undefined
  }

  return undefined
}

function NumberInputRenderer({ props }: ComponentRenderProps<NumberInputProps>) {
  const isStreaming = useIsStreaming()
  const fieldId = useId()
  const field = useFormField<NumberFieldValue>({
    componentType: 'NumberInput',
    name: props.name,
    ...(props.defaultValue === undefined ? {} : { defaultValue: props.defaultValue }),
    fallback: '',
    parse: parseNumberField,
  })

  const handleChange = (raw: string): void => {
    if (raw === '') {
      field.setValue('')
      return
    }

    const parsed = Number(raw)
    if (Number.isFinite(parsed)) {
      field.setValue(parsed)
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      <OpenUiLabel htmlFor={fieldId}>{props.label}</OpenUiLabel>
      {props.description ? <p className="text-xs text-muted-foreground">{props.description}</p> : null}
      <OpenUiInput
        id={fieldId}
        size="medium"
        type="number"
        value={field.value}
        disabled={isStreaming}
        {...(props.placeholder === undefined ? {} : { placeholder: props.placeholder })}
        {...(props.min === undefined ? {} : { min: props.min })}
        {...(props.max === undefined ? {} : { max: props.max })}
        {...(props.step === undefined ? {} : { step: props.step })}
        onChange={(event) => handleChange(event.target.value)}
      />
    </div>
  )
}

/** 数字输入：空值存为空字符串，避免把「未填写」误报成 0 */
export const NumberInput = defineComponent({
  name: 'NumberInput',
  description: '数字输入框，用于数量、金额、年龄等数值',
  props: z.object({
    name: z.string().min(1).max(64).describe('字段名，提交时作为表单键'),
    label: z.string().describe('字段标题'),
    placeholder: z.string().optional().describe('输入提示'),
    defaultValue: z.number().optional().describe('默认值'),
    min: z.number().optional().describe('允许的最小值'),
    max: z.number().optional().describe('允许的最大值'),
    step: z.number().optional().describe('步长'),
    description: z.string().optional().describe('字段下方的补充说明'),
  }),
  component: NumberInputRenderer,
})
