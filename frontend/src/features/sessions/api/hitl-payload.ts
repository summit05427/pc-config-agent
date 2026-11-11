import type { HitlField, HitlInterrupt } from './types'

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const toText = (value: unknown, fallback = ''): string =>
  typeof value === 'string' ? value : fallback

/** 中断表单字段；缺 name/label 的字段无法渲染，直接丢弃该字段。 */
const toHitlFields = (value: unknown): HitlField[] => {
  if (!Array.isArray(value)) {
    return []
  }
  const fields: HitlField[] = []
  for (const item of value) {
    if (!isRecord(item)) {
      continue
    }
    const name = toText(item.name)
    const label = toText(item.label)
    if (!name || !label) {
      continue
    }
    const field: HitlField = {
      name,
      label,
      type: toText(item.type, 'text'),
      required: item.required === true,
    }
    if (typeof item.min === 'number') {
      field.min = item.min
    }
    if (Array.isArray(item.options)) {
      field.options = item.options.flatMap((option) => {
        if (!isRecord(option)) {
          return []
        }
        const optionValue = toText(option.value)
        const optionLabel = toText(option.label)
        return optionValue && optionLabel ? [{ value: optionValue, label: optionLabel }] : []
      })
    }
    fields.push(field)
  }
  return fields
}

/**
 * 把服务端原始中断载荷解析为前端表单结构。
 *
 * SSE 的 `interrupt` 事件与历史消息的 `hitl` 字段携带的是同一份后端载荷
 * （snake_case + `input_schema`），必须走同一个解析入口：历史路径曾直接透传原始
 * 载荷，导致 `fields` 缺失并让整个路由进入错误边界。载荷缺关键字段时返回 null，
 * 调用方跳过而不是渲染一个无法提交的空表单。
 */
export const parseHitlInterrupt = (raw: unknown): HitlInterrupt | null => {
  if (!isRecord(raw)) {
    return null
  }
  const interruptId = toText(raw.interrupt_id)
  const interactionType = toText(raw.interaction_type)
  const question = toText(raw.question)
  if (!interruptId || !interactionType || !question) {
    return null
  }
  const schema = isRecord(raw.input_schema) ? raw.input_schema : {}
  const interrupt: HitlInterrupt = {
    interruptId,
    interactionType,
    question,
    fields: toHitlFields(schema.fields),
    submitLabel: toText(schema.submit_label, '提交'),
    context: isRecord(raw.context) ? raw.context : {},
  }
  if (typeof raw.schema_version === 'string') {
    interrupt.schemaVersion = raw.schema_version
  }
  return interrupt
}
