/** 管理端模型目录与定价的展示类型，字段与 `/api/v1/admin/**` 响应保持一致。 */
export interface ModelPricingVersion {
  id: number
  currency: string
  inputPricePerMillion: number
  outputPricePerMillion: number
  effectiveFrom: string
  createdAt: string
}

export interface AdminModelSummary {
  provider: string
  modelKey: string
  displayName: string
  contextWindow: number | null
  capabilities: string[]
  capabilitySource: string
  verifiedAt: string | null
  enabled: boolean
  providerEnabled: boolean
  latestPricing: ModelPricingVersion | null
}

export interface AdminProviderSummary {
  code: string
  displayName: string
  protocol: string
  defaultBaseUrl: string | null
  enabled: boolean
  modelCount: number
  enabledModelCount: number
}

export const MODEL_ENABLED_FILTERS = ['', 'true', 'false'] as const
export type ModelEnabledFilter = (typeof MODEL_ENABLED_FILTERS)[number]

/** 能力来源是协议字段（catalog / verified），展示文案在本地映射，不改协议值。 */
export const CAPABILITY_SOURCE_LABELS: Record<string, string> = {
  catalog: '目录声明',
  verified: '实测验证',
}
