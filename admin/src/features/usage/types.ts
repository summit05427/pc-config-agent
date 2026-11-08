/**
 * 管理端用量与成本展示类型，字段与 `/api/v1/admin/model-usage*` 响应保持一致。
 *
 * 金额可能为空：多币种不可求和或无定价时由服务端置空，前端不得自行推算。
 */
export interface AdminUsageItem {
  invocationId: string
  taskId: string
  userId: string
  username: string
  threadId: string
  modelRole: string
  provider: string
  modelKey: string
  credentialSource: string
  promptTokens: number | null
  completionTokens: number | null
  latencyMs: number | null
  status: string
  errorType: string | null
  estimatedCost: number | null
  costStatus: string
  costBearer: string
  currency: string | null
  occurredAt: string
}

export interface AdminUsageTotals {
  requestCount: number
  successCount: number
  failureCount: number
  promptTokens: number
  completionTokens: number
  totalTokens: number
  estimatedCost: number | null
  currency: string | null
  estimatedCount: number
  unknownCostCount: number
  byokNotBilledCount: number
}

export interface AdminUsageCostStatusBreakdown {
  costStatus: string
  requestCount: number
  estimatedCost: number | null
  currency: string | null
}

export interface AdminUsageProviderBreakdown {
  provider: string
  requestCount: number
  promptTokens: number
  completionTokens: number
  totalTokens: number
  estimatedCost: number | null
  currency: string | null
}

export interface AdminUsageModelBreakdown {
  provider: string
  modelKey: string
  requestCount: number
  promptTokens: number
  completionTokens: number
  totalTokens: number
  estimatedCost: number | null
  currency: string | null
}

export interface AdminUsageSummary {
  from: string | null
  to: string | null
  totals: AdminUsageTotals
  byCostStatus: AdminUsageCostStatusBreakdown[]
  byProvider: AdminUsageProviderBreakdown[]
  byModel: AdminUsageModelBreakdown[]
}

/** 凭证来源是协议字段，展示文案在本地映射，不改协议值。 */
export const CREDENTIAL_SOURCES = ['MANAGED', 'BYOK'] as const
export type CredentialSource = (typeof CREDENTIAL_SOURCES)[number]

export const COST_STATUSES = ['ESTIMATED', 'UNKNOWN', 'BYOK_NOT_BILLED'] as const
export type CostStatus = (typeof COST_STATUSES)[number]

export const USAGE_RESULTS = ['success', 'failure'] as const
export type UsageResult = (typeof USAGE_RESULTS)[number]

export const USAGE_ORDERS = ['desc', 'asc'] as const
export type UsageOrder = (typeof USAGE_ORDERS)[number]

export const CREDENTIAL_SOURCE_LABELS: Record<CredentialSource, string> = {
  MANAGED: '平台托管',
  BYOK: '用户自带',
}

export const COST_STATUS_LABELS: Record<CostStatus, string> = {
  ESTIMATED: '已估算',
  UNKNOWN: '费用未知',
  BYOK_NOT_BILLED: 'BYOK 不计费',
}

export const USAGE_RESULT_LABELS: Record<UsageResult, string> = {
  success: '成功',
  failure: '失败',
}

export const USAGE_ORDER_LABELS: Record<UsageOrder, string> = {
  desc: '时间倒序',
  asc: '时间正序',
}

/** 成本状态是未知值时原样展示，避免管理端因新增枚举直接显示空白。 */
export function getCostStatusLabel(value: string): string {
  return COST_STATUS_LABELS[value as CostStatus] ?? value
}

export function getCredentialSourceLabel(value: string): string {
  return CREDENTIAL_SOURCE_LABELS[value as CredentialSource] ?? value
}

export function getUsageResultLabel(value: string): string {
  return USAGE_RESULT_LABELS[value as UsageResult] ?? value
}
