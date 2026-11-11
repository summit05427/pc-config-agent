import type { ActionEvent } from '@openuidev/react-lang'

import type { OpenUiFormFieldValue, OpenUiFormSubmission } from '../../types'
import { OPEN_BUILD_DETAIL_ACTION } from './build-detail'

/** 只有白名单内的动作允许到达宿主应用；其余类型一律丢弃 */
export const ALLOWED_OPENUI_ACTION_TYPES = [
  'open_url',
  'continue_conversation',
  OPEN_BUILD_DETAIL_ACTION,
] as const

export type AllowedOpenUiActionType = (typeof ALLOWED_OPENUI_ACTION_TYPES)[number]

export type OpenUiActionDispatchResult = 'handled' | 'rejected' | 'ignored'

const SAFE_OPEN_URL_PROTOCOLS = new Set(['http:', 'https:'])

/** 单次提交最多接收的字段数：防止模型生成超长 payload 拖慢消息序列化 */
const MAX_FORM_FIELDS = 50

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function readFieldValue(raw: unknown): OpenUiFormFieldValue | undefined {
  if (typeof raw === 'string' || typeof raw === 'number' || typeof raw === 'boolean') {
    return raw
  }

  if (Array.isArray(raw) && raw.every((item) => typeof item === 'string')) {
    return raw
  }

  return undefined
}

function readFields(raw: unknown): Record<string, OpenUiFormFieldValue> {
  if (!isPlainRecord(raw)) {
    return {}
  }

  const fields: Record<string, OpenUiFormFieldValue> = {}
  let fieldCount = 0

  for (const [name, entry] of Object.entries(raw)) {
    if (fieldCount >= MAX_FORM_FIELDS) {
      break
    }

    // 运行时把字段存成 { value, componentType }，同时兼容直接存原始值
    const value = isPlainRecord(entry) ? readFieldValue(entry.value) : readFieldValue(entry)
    if (value === undefined) {
      continue
    }

    fields[name] = value
    fieldCount += 1
  }

  return fields
}

function formatFieldValue(value: OpenUiFormFieldValue): string {
  return Array.isArray(value) ? value.join('、') : String(value)
}

/**
 * 从动作事件中提取表单值。
 *
 * Runtime 的 formState 形状是 { [formName]: { [field]: { value, componentType } } }；
 * 没有表单名时退化为直接以字段名为键，两种形状都要兼容。
 */
export function extractOpenUiFormSubmission(event: ActionEvent): OpenUiFormSubmission | null {
  const { formState, formName } = event
  if (!isPlainRecord(formState)) {
    return null
  }

  const scoped = formName !== undefined && isPlainRecord(formState[formName]) ? formState[formName] : formState
  const fields = readFields(scoped)

  if (Object.keys(fields).length === 0) {
    return null
  }

  return {
    ...(formName === undefined ? {} : { formName }),
    fields,
    message: Object.entries(fields)
      .map(([name, value]) => `- ${name}: ${formatFieldValue(value)}`)
      .join('\n'),
  }
}

function mergeFormMessage(baseMessage: string, submission: OpenUiFormSubmission): string {
  const header = baseMessage.trim() || '提交表单'
  return `${header}\n\n${submission.message}`
}

/**
 * 只放行绝对 http/https 地址。
 *
 * javascript:、data:、file: 以及相对路径全部拒绝：相对路径在聊天上下文中
 * 没有可信基址，交给宿主解析反而扩大攻击面。
 */
export function isSafeOpenUrl(value: unknown): value is string {
  if (typeof value !== 'string') {
    return false
  }

  try {
    return SAFE_OPEN_URL_PROTOCOLS.has(new URL(value.trim()).protocol)
  } catch {
    return false
  }
}

export interface OpenUiActionHandlers {
  readonly onOpenUrl?: (url: string) => void
  readonly onContinueConversation?: (message: string) => void
  /** 表单提交时优先回调；未提供时退化为把字段文本并入继续对话消息 */
  readonly onSubmitForm?: (submission: OpenUiFormSubmission) => void
  /** 打开宿主固定样式详情面板；不消费动作参数，数据来自当前消息的 buildResult */
  readonly onOpenBuildDetail?: () => void
}

const isAllowedActionType = (type: string): type is AllowedOpenUiActionType =>
  (ALLOWED_OPENUI_ACTION_TYPES as readonly string[]).includes(type)

/**
 * 把 ActionEvent 转发给宿主回调。
 *
 * 这里是生成式 UI 的唯一动作出口：组件与 Renderer 都不直接打开链接或发请求，
 * 未注册的动作与非法 URL 在进入回调前就会被拦下。
 */
export function dispatchOpenUiAction(
  event: ActionEvent,
  handlers: OpenUiActionHandlers,
): OpenUiActionDispatchResult {
  if (!isAllowedActionType(event.type)) {
    return 'ignored'
  }

  if (event.type === 'open_url') {
    const url = event.params.url
    if (!isSafeOpenUrl(url)) {
      return 'rejected'
    }
    if (!handlers.onOpenUrl) {
      return 'ignored'
    }
    handlers.onOpenUrl(url.trim())
    return 'handled'
  }

  if (event.type === OPEN_BUILD_DETAIL_ACTION) {
    if (!handlers.onOpenBuildDetail) {
      return 'ignored'
    }
    handlers.onOpenBuildDetail()
    return 'handled'
  }

  if (event.type === 'continue_conversation') {
    const submission = extractOpenUiFormSubmission(event)

    // 表单提交优先走专用回调，宿主可把字段写进消息元数据而不是拼进正文
    if (submission && handlers.onSubmitForm) {
      handlers.onSubmitForm(submission)
      return 'handled'
    }

    const message = submission
      ? mergeFormMessage(event.humanFriendlyMessage, submission)
      : event.humanFriendlyMessage.trim()
    // 空消息不触发新一轮对话，避免模型用空按钮刷请求或计费
    if (!message || !handlers.onContinueConversation) {
      return 'ignored'
    }
    handlers.onContinueConversation(message)
    return 'handled'
  }

  return 'ignored'
}
