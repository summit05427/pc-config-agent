import { http } from '@/core/http'
import { env } from '@/shared/lib/env'
import type { PageResult } from '@/shared/types/http'

/**
 * 模型目录条目，字段命名与 Java `ModelSummaryResponse` 保持一致（camelCase）。
 *
 * `modelKey` 是完整引用 `<provider>:<modelKey>`，可直接作为 Agent 的 `model` 字段。
 */
export interface ModelCatalogItem {
  provider: string
  modelKey: string
  displayName: string
  capabilities: string[]
  /** 上下文窗口未知时服务端返回 null，展示层需自行兜底 */
  contextWindow: number | null
}

export interface ModelListQuery {
  page?: number
  size?: number
}

/**
 * 目录与连接列表都是小集合，前端一次取满服务端上限 100；
 * 不传时服务端默认只给 20 条，会把模型目录悄悄截断。
 */
export const MODEL_LIST_QUERY = { page: 1, size: 100 } as const

/**
 * 分页查询当前用户可用的模型目录（v2）。
 *
 * v2 与 v1 只是版本段不同，必须显式指定 `baseURL`，否则会被拼成 `/api/v1/v2/models`。
 * 运行时未启用时服务端返回 404；这里用 silent 关闭全局 toast，
 * 由调用方隐藏模型选择器并保持对话可用。
 */
export const listModels = (
  query: ModelListQuery = MODEL_LIST_QUERY,
): Promise<PageResult<ModelCatalogItem>> =>
  http.get<PageResult<ModelCatalogItem>>('/models', {
    baseURL: env.apiV2BaseUrl,
    params: query,
    silent: true,
  })

/**
 * 可接入 Provider 摘要，字段与 Java `ModelProviderSummary` 对齐（camelCase）。
 *
 * 服务端只返回协议受支持的 Provider，并附带平台目录中的模型数量；
 * `defaultBaseUrl` 为空表示该 Provider 没有默认接入地址。
 */
export interface ModelProviderSummary {
  code: string
  displayName: string
  protocol: string
  defaultBaseUrl: string | null
  modelCount: number
}

/** 列出可接入的 Provider（v2）；与模型目录、连接接口一致，运行时未启用时返回 404 */
export const listModelProviders = (): Promise<ModelProviderSummary[]> =>
  http.get<ModelProviderSummary[]>('/model-providers', {
    baseURL: env.apiV2BaseUrl,
    silent: true,
  })

/** 凭证摘要：服务端只回传掩码，不存在明文或密文回读接口 */
export interface ModelConnectionCredential {
  id: string
  maskedHint: string
  status: string
  createdAt: string
}

/** BYOK 连接，字段与 Java `ModelConnectionResponse` 对齐 */
export interface ModelConnection {
  id: string
  provider: string
  providerName: string
  baseUrl: string
  status: string
  lastVerifiedAt: string | null
  createdAt: string
  credential: ModelConnectionCredential | null
}

export interface ModelConnectionCreatePayload {
  providerCode: string
  /** 留空表示使用 Provider 默认地址 */
  baseUrl?: string | null
  apiKey: string
}

/** 分页列出当前用户的 BYOK 连接（v2）；BYOK 未启用时返回 404，调用方据此隐藏整块 */
export const listModelConnections = (
  query: ModelListQuery = MODEL_LIST_QUERY,
): Promise<PageResult<ModelConnection>> =>
  http.get<PageResult<ModelConnection>>('/model-connections', {
    baseURL: env.apiV2BaseUrl,
    params: query,
    silent: true,
  })

/** 创建连接并保存加密凭证；同一 Provider 重复创建返回 409 */
export const createModelConnection = (
  payload: ModelConnectionCreatePayload,
): Promise<ModelConnection> => http.post<ModelConnection>('/model-connections', payload)

export interface ModelConnectionUpdatePayload {
  /** 留空表示沿用原接入地址 */
  baseUrl?: string | null
  /** 新明文密钥，服务端加密后只回传掩码 */
  apiKey: string
}

/** 轮换凭证：撤销旧凭证并写入新密钥，保存后服务端自动验证一次 */
export const updateModelConnection = (
  connectionId: string,
  payload: ModelConnectionUpdatePayload,
): Promise<ModelConnection> =>
  http.put<ModelConnection>(`/model-connections/${encodeURIComponent(connectionId)}`, payload)

/** 手动重新验证凭证：服务端会真实探测上游，单用户每分钟有调用上限 */
export const verifyModelConnection = (connectionId: string): Promise<ModelConnection> =>
  http.post<ModelConnection>(`/model-connections/${encodeURIComponent(connectionId)}/verify`)

/** 软删除连接并撤销凭证，撤销后凭证不可再使用 */
export const deleteModelConnection = (connectionId: string): Promise<void> =>
  http.delete<void>(`/model-connections/${encodeURIComponent(connectionId)}`)
