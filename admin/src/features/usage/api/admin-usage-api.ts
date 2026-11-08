import { z } from 'zod'
import { queryOptions } from '@tanstack/react-query'
import { httpJson } from '@/core/http/client'
import type { PageResult } from '@/core/http/types'
import { queryKeys } from '@/lib/query-keys'
import {
  COST_STATUSES,
  CREDENTIAL_SOURCES,
  USAGE_RESULTS,
  type AdminUsageItem,
  type AdminUsageSummary,
  type CostStatus,
  type CredentialSource,
  type UsageOrder,
  type UsageResult,
} from '../types'

const nullableNumber = z
  .number()
  .nullish()
  .transform((value) => value ?? null)

const usageItemSchema = z.object({
  invocationId: z.string(),
  taskId: z.string(),
  userId: z.string(),
  username: z.string(),
  threadId: z.string(),
  modelRole: z.string(),
  provider: z.string(),
  modelKey: z.string(),
  credentialSource: z.enum(CREDENTIAL_SOURCES),
  promptTokens: nullableNumber,
  completionTokens: nullableNumber,
  latencyMs: nullableNumber,
  status: z.enum(USAGE_RESULTS),
  errorType: z
    .string()
    .nullish()
    .transform((value) => value ?? null),
  estimatedCost: nullableNumber,
  costStatus: z.enum(COST_STATUSES),
  costBearer: z.string(),
  currency: z
    .string()
    .nullish()
    .transform((value) => value ?? null),
  occurredAt: z.string().min(1),
})

const usagePageSchema = z.object({
  list: z.array(usageItemSchema),
  total: z.number(),
  page: z.number(),
  size: z.number(),
})

const totalsSchema = z.object({
  requestCount: z.number(),
  successCount: z.number(),
  failureCount: z.number(),
  promptTokens: z.number(),
  completionTokens: z.number(),
  totalTokens: z.number(),
  estimatedCost: nullableNumber,
  currency: z
    .string()
    .nullish()
    .transform((value) => value ?? null),
  estimatedCount: z.number(),
  unknownCostCount: z.number(),
  byokNotBilledCount: z.number(),
})

const costStatusBreakdownSchema = z.object({
  costStatus: z.enum(COST_STATUSES),
  requestCount: z.number(),
  estimatedCost: nullableNumber,
  currency: z
    .string()
    .nullish()
    .transform((value) => value ?? null),
})

const providerBreakdownSchema = z.object({
  provider: z.string(),
  requestCount: z.number(),
  promptTokens: z.number(),
  completionTokens: z.number(),
  totalTokens: z.number(),
  estimatedCost: nullableNumber,
  currency: z
    .string()
    .nullish()
    .transform((value) => value ?? null),
})

const modelBreakdownSchema = providerBreakdownSchema.extend({
  modelKey: z.string(),
})

const usageSummarySchema = z.object({
  from: z
    .string()
    .nullish()
    .transform((value) => value ?? null),
  to: z
    .string()
    .nullish()
    .transform((value) => value ?? null),
  totals: totalsSchema,
  byCostStatus: z.array(costStatusBreakdownSchema),
  byProvider: z.array(providerBreakdownSchema),
  byModel: z.array(modelBreakdownSchema),
})

export interface AdminUsageListParams {
  page: number
  size: number
  userId?: string
  provider?: string
  modelKey?: string
  credentialSource?: CredentialSource | ''
  costStatus?: CostStatus | ''
  status?: UsageResult | ''
  from?: string
  to?: string
  order?: UsageOrder
}

export interface AdminUsageSummaryParams {
  provider?: string
  modelKey?: string
  credentialSource?: CredentialSource | ''
  from?: string
  to?: string
}

/** 使用明细：过滤、分页与排序全部由服务端执行。 */
export async function fetchAdminUsage(
  params: AdminUsageListParams
): Promise<PageResult<AdminUsageItem>> {
  return usagePageSchema.parse(
    await httpJson<unknown>({
      url: '/admin/model-usage',
      method: 'get',
      params: {
        page: params.page,
        size: params.size,
        userId: params.userId || undefined,
        provider: params.provider || undefined,
        modelKey: params.modelKey || undefined,
        credentialSource: params.credentialSource || undefined,
        costStatus: params.costStatus || undefined,
        status: params.status || undefined,
        from: params.from || undefined,
        to: params.to || undefined,
        order: params.order || undefined,
      },
    })
  )
}

export const adminUsageListQueryOptions = (params: AdminUsageListParams) =>
  queryOptions({
    queryKey: [...queryKeys.adminUsage.all, 'list', params],
    queryFn: () => fetchAdminUsage(params),
  })

/** 用量聚合：与列表同一 UTC 自然日口径，多币种金额由服务端置空。 */
export async function fetchAdminUsageSummary(
  params: AdminUsageSummaryParams
): Promise<AdminUsageSummary> {
  return usageSummarySchema.parse(
    await httpJson<unknown>({
      url: '/admin/model-usage/summary',
      method: 'get',
      params: {
        provider: params.provider || undefined,
        modelKey: params.modelKey || undefined,
        credentialSource: params.credentialSource || undefined,
        from: params.from || undefined,
        to: params.to || undefined,
      },
    })
  )
}

export const adminUsageSummaryQueryOptions = (
  params: AdminUsageSummaryParams
) =>
  queryOptions({
    queryKey: [...queryKeys.adminUsage.all, 'summary', params],
    queryFn: () => fetchAdminUsageSummary(params),
  })
