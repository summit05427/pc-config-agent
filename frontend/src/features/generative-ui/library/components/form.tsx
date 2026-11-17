import { createContext, useContext } from 'react'
import {
  type ComponentRenderProps,
  defineComponent,
  FormNameContext,
  type SubComponentOf,
} from '@openuidev/react-lang'
import { FormControl } from '@openuidev/react-ui/FormControl'
import { z } from 'zod'

import { ActionGroup } from './action-group'
import { Button } from './button'
import { CheckboxGroup } from './checkbox-group'
import { NumberInput } from './number-input'
import { RadioGroup } from './radio-group'
import { Select } from './select'
import { TextInput } from './text-input'

type FormProps = {
  name: string
  buttons: SubComponentOf<{ label: string }> | SubComponentOf<{ buttons: unknown[] }>
  fields: SubComponentOf<Record<string, unknown>>[]
}

/** 表单可容纳的字段组件，限制联合类型让模型生成的字段一定可解析 */
const FORM_FIELD = z.union([
  TextInput.ref,
  NumberInput.ref,
  Select.ref,
  CheckboxGroup.ref,
  RadioGroup.ref,
])

/**
 * HITL 待澄清时由宿主置为 true：澄清表单与生成式表单是双入口，
 * 同时出现会让用户不知道在哪提交，渲染层直接隐藏 Form。
 */
export const FormDisabledContext = createContext(false)

function FormRenderer({ props, renderNode }: ComponentRenderProps<FormProps>) {
  const isFormDisabled = useContext(FormDisabledContext)
  const fields = props.fields ?? []
  if (fields.length === 0 || isFormDisabled) {
    return null
  }

  return (
    // 官方 FormControl 负责字段容器与错误态上下文，表面样式经 className 对齐 CDS Token
    <FormControl className="flex flex-col gap-4 rounded-lg border border-border bg-card p-4">
      <FormNameContext.Provider value={props.name}>
        {renderNode(fields)}
        {renderNode(props.buttons)}
      </FormNameContext.Provider>
    </FormControl>
  )
}

/**
 * 表单容器。
 *
 * 只提供表单名与布局，字段值由各输入组件写入 OpenUI 运行时 store；
 * 按钮位于 FormNameContext 内，点击时 Runtime 会把全部字段值一并回传。
 */
export const Form = defineComponent({
  name: 'Form',
  description: '表单：把输入字段与提交按钮组合，提交时回传全部字段值',
  props: z.object({
    name: z.string().min(1).max(64).describe('表单名称，提交时作为来源标识'),
    buttons: z
      .union([Button.ref, ActionGroup.ref])
      .describe('提交按钮，单个 Button 或 ActionGroup'),
    fields: z.array(FORM_FIELD).min(1).describe('表单字段列表，至少一个输入组件'),
  }),
  component: FormRenderer,
})
