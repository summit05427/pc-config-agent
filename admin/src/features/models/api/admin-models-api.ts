import { z } from 'zod'
import { queryOptions } from '@tanstack/react-query'
import { httpJson } from '@/core/http/client'
import type { PageResult } from '@/core/http/types'
import { queryKeys } from '@/lib/query-keys'
import type {
  AdminModelSummary,
  AdminProviderSummary,
  ModelEnabledFilter,
  ModelPricingVersion,
} from '../types'

const pricingSchema = z.object({
  id: z.number(),
  currency: z.string(),
  inputPricePerMillion: z.number(),
  outputPricePerMillion: z.number(),
  effectiveFrom: z.string().min(1),
  createdAt: z.string().min(1),
})

const modelSchema = z.object({
  provider: z.string().min(1),
  modelKey: z.string().min(1),
  displayName: z.string().min(1),
  contextWindow: z
    .number()
    .nullish()
    .transform((value) => value ?? null),
  capabilities: z.array(z.string()),
  capabilitySource: z.string(),
  verifiedAt: z
    .string()
    .nullish()
    .transform((value) => value ?? null),
  enabled: z.boolean(),
  providerEnabled: z.boolean(),
  latestPricing: pricingSchema
    .nullish()
    .transform((value) => value ?? null),
})

const modelPageSchema = z.object({
  list: z.array(modelSchema),
  total: z.number(),
  page: z.number(),
  size: z.number(),
})

const pricingPageSchema = z.object({
  list: z.array(pricingSchema),
  total: z.number(),
  page: z.number(),
  size: z.number(),
})

const providerSchema = z.object({
  code: z.string().min(1),
  displayName: z.string().min(1),
  protocol: z.string(),
  defaultBaseUrl: z
    .string()
    .nullish()
    .transform((value) => value ?? null),
  enabled: z.boolean(),
  modelCount: z.number(),
  enabledModelCount: z.number(),
})

export interface AdminModelListParams {
  page: number
  size: number
  keyword?: string
  provider?: string
  enabled?: ModelEnabledFilter
}

export interface CreateModelPricingInput {
  currency: string
  inputPricePerMillion: number
  outputPricePerMillion: number
  effectiveFrom: string
}

/** 管理端模型目录：含停用条目，过滤与分页全部由服务端处理。 */
export async function fetchAdminModels(
  params: AdminModelListParams
): Promise<PageResult<AdminModelSummary>> {
  return modelPageSchema.parse(
    await httpJson<unknown>({
      url: '/admin/models',
      method: 'get',
      params: {
        page: params.page,
        size: params.size,
        keyword: params.keyword || undefined,
        provider: params.provider || undefined,
        enabled: params.enabled || undefined,
      },
    })
  )
}

export const adminModelsQueryOptions = (params: AdminModelListParams) =>
  queryOptions({
    queryKey: [...queryKeys.adminModels.all, 'list', params],
    queryFn: () => fetchAdminModels(params),
  })

/** 启用/停用模型；停用只影响后续调用解析，不删除目录条目。 */
export async function updateModelStatus(
  provider: string,
  modelKey: string,
  enabled: boolean
): Promise<AdminModelSummary> {
  return modelSchema.parse(
    await httpJson<unknown>({
      url: `/admin/models/${encodeURIComponent(provider)}/${encodeURIComponent(modelKey)}/status`,
      method: 'patch',
      data: { enabled },
    })
  )
}

export interface ModelPricingListParams {
  page: number
  size: number
}

/** 定价版本列表，按生效时间倒序。 */
export async function fetchModelPricing(
  provider: string,
  modelKey: string,
  params: ModelPricingListParams
): Promise<PageResult<ModelPricingVersion>> {
  return pricingPageSchema.parse(
    await httpJson<unknown>({
      url: `/admin/models/${encodeURIComponent(provider)}/${encodeURIComponent(modelKey)}/pricing`,
      method: 'get',
      params,
    })
  )
}

export const modelPricingQueryOptions = (
  provider: string,
  modelKey: string,
  params: ModelPricingListParams
) =>
  queryOptions({
    queryKey: [
      ...queryKeys.adminModels.all,
      'pricing',
      provider,
      modelKey,
      params,
    ],
    queryFn: () => fetchModelPricing(provider, modelKey, params),
  })

/** 追加定价版本；同一生效时间重复提交由服务端返回 409。 */
export async function createModelPricing(
  provider: string,
  modelKey: string,
  input: CreateModelPricingInput
): Promise<ModelPricingVersion> {
  return pricingSchema.parse(
    await httpJson<unknown>({
      url: `/admin/models/${encodeURIComponent(provider)}/${encodeURIComponent(modelKey)}/pricing`,
      method: 'post',
      data: input,
    })
  )
}

export async function fetchAdminProviders(): Promise<AdminProviderSummary[]> {
  return z
    .array(providerSchema)
    .parse(await httpJson<unknown>({ url: '/admin/model-providers', method: 'get' }))
}

export const adminProvidersQueryOptions = () =>
  queryOptions({
    queryKey: [...queryKeys.modelProviders.all, 'list'],
    queryFn: fetchAdminProviders,
  })

/** 启用/停用 Provider；停用后其下模型即使启用也不可用。 */
export async function updateProviderStatus(
  code: string,
  enabled: boolean
): Promise<AdminProviderSummary> {
  return providerSchema.parse(
    await httpJson<unknown>({
      url: `/admin/model-providers/${encodeURIComponent(code)}/status`,
      method: 'patch',
      data: { enabled },
    })
  )
}
