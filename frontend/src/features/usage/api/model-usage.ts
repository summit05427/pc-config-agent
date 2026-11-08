import { http } from '@/core/http'

/** 当日额度快照，字段与 Java `ModelUsageResponse.QuotaResponse` 对齐 */
export interface ModelUsageQuota {
  quotaType: string
  limit: number
  used: number
  /** 额度重置时间，固定为次日 00:00Z */
  resetAt: string
}

/** 单条使用明细，字段与 Java `ModelUsageItemResponse` 对齐 */
export interface ModelUsageItem {
  invocationId: string
  taskId: string
  threadId: string
  modelRole: string
  provider: string
  modelKey: string
  /** 凭证来源：MANAGED（平台密钥）/ BYOK（用户自带） */
  credentialSource: string
  /** 上游未返回用量时服务端保持 null，展示层不得当作 0 */
  promptTokens: number | null
  completionTokens: number | null
  latencyMs: number | null
  status: string
  errorType: string | null
  /** 成本状态：ESTIMATED / UNKNOWN / BYOK_NOT_BILLED */
  costStatus: string
  /** 成本承担方：PLATFORM（平台）/ USER（用户） */
  costBearer: string
  /** 成本币种；仅 ESTIMATED 时存在 */
  currency: string | null
  /** 预估费用；非 ESTIMATED 时为 null，展示层不得当作 0 */
  estimatedCost: number | null
  occurredAt: string
}

/** 用量查询参数；日期为 UTC 自然日，闭区间 */
export interface ModelUsageQuery {
  page?: number
  size?: number
  from?: string
  to?: string
}

/** 用量响应，字段与 Java `ModelUsageResponse` 对齐 */
export interface ModelUsagePage {
  quota: ModelUsageQuota
  list: ModelUsageItem[]
  total: number
  page: number
  size: number
  /** 累计消耗 Token 数（输入 + 输出，全时段） */
  totalTokens: number
}

/**
 * 查询本人模型用量。
 *
 * 运行时未启用时服务端返回 404，用 silent 由调用方隐藏入口；
 * 分页或日期参数非法返回 400。
 */
export const getMyModelUsage = (query: ModelUsageQuery = {}): Promise<ModelUsagePage> =>
  http.get<ModelUsagePage>('/users/me/model-usage', { params: query, silent: true })
