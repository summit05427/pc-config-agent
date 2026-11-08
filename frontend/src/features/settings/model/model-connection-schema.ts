import { z } from 'zod'

import type {
  ModelConnectionCreatePayload,
  ModelConnectionUpdatePayload,
} from '@/features/models/api'

export interface ModelConnectionFormValues {
  providerCode: string
  baseUrl: string
  apiKey: string
}

export interface ModelCredentialFormValues {
  baseUrl: string
  apiKey: string
}

type Translate = (key: string, options?: Record<string, unknown>) => string

export const MIN_API_KEY_LENGTH = 8
const BASE_URL_MAX = 255
const API_KEY_MAX = 512

/** 只接受 http/https，与 Java BaseUrlPolicy 的协议白名单一致 */
export const isHttpUrl = (value: string): boolean => {
  if (value === '') {
    return true
  }

  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

// 地址与密钥的规则只在这里维护；新建表单与轮换弹窗共用，避免两套校验漂移
const baseUrlField = (t: Translate) =>
  z
    .string()
    .trim()
    .max(BASE_URL_MAX, { message: t('settings.errors.tooLong', { max: BASE_URL_MAX }) })
    .refine(isHttpUrl, { message: t('settings.errors.invalidUrl') })

const apiKeyField = (t: Translate) =>
  z
    .string()
    .trim()
    .min(MIN_API_KEY_LENGTH, { message: t('settings.errors.apiKeyTooShort') })
    .max(API_KEY_MAX, { message: t('settings.errors.tooLong', { max: API_KEY_MAX }) })

/** 模型连接新建表单：Provider 必选、地址可留空、密钥至少 8 位 */
export function createModelConnectionSchema(t: Translate) {
  return z.object({
    providerCode: z.string().trim().min(1, { message: t('settings.errors.required') }),
    baseUrl: baseUrlField(t),
    apiKey: apiKeyField(t),
  })
}

/** 凭证轮换：只换地址与密钥，Provider 由连接本身决定 */
export function createModelCredentialSchema(t: Translate) {
  return z.object({
    baseUrl: baseUrlField(t),
    apiKey: apiKeyField(t),
  })
}

/** 空白地址转 null，与服务端「留空使用 Provider 默认地址」的语义一致 */
export const toModelConnectionPayload = (
  values: ModelConnectionFormValues,
): ModelConnectionCreatePayload => ({
  providerCode: values.providerCode,
  baseUrl: values.baseUrl.trim() === '' ? null : values.baseUrl.trim(),
  apiKey: values.apiKey.trim(),
})

export const toModelCredentialPayload = (
  values: ModelCredentialFormValues,
): ModelConnectionUpdatePayload => ({
  baseUrl: values.baseUrl.trim() === '' ? null : values.baseUrl.trim(),
  apiKey: values.apiKey.trim(),
})

export { API_KEY_MAX, BASE_URL_MAX }
