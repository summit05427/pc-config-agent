import {
  useFormName,
  useGetFieldValue,
  useSetDefaultValue,
  useSetFieldValue,
} from '@openuidev/react-lang'

/** 字段值解析器：把运行时 store 里的 unknown 收窄成组件可用的类型 */
export type FormFieldParser<T> = (raw: unknown) => T | undefined

interface FormFieldOptions<T> {
  /** 注册到表单状态时的组件标识，用于运行时区分字段来源 */
  readonly componentType: string
  /** 字段名，提交时作为表单键 */
  readonly name: string
  readonly defaultValue?: T
  readonly fallback: T
  readonly parse: FormFieldParser<T>
}

export interface FormFieldBinding<T> {
  readonly value: T
  readonly setValue: (next: T) => void
}

/**
 * 把组件字段接入 OpenUI 表单状态。
 *
 * 读写都经运行时 store，保证 Form 提交时拿到用户最新输入；
 * 写入时关闭保存回调，避免每次按键都触发消息持久化。
 */
export function useFormField<T>({
  componentType,
  name,
  defaultValue,
  fallback,
  parse,
}: FormFieldOptions<T>): FormFieldBinding<T> {
  const formName = useFormName()
  const getFieldValue = useGetFieldValue()
  const setFieldValue = useSetFieldValue()
  const rawValue: unknown = getFieldValue(formName, name)

  // 默认值在流式结束后写入，已存在的用户输入不会被覆盖
  useSetDefaultValue({
    ...(formName === undefined ? {} : { formName }),
    componentType,
    name,
    existingValue: rawValue,
    defaultValue,
  })

  const parsedValue = rawValue === undefined ? undefined : parse(rawValue)

  return {
    value: parsedValue ?? defaultValue ?? fallback,
    setValue: (next: T) => {
      setFieldValue(formName, componentType, name, next, false)
    },
  }
}
