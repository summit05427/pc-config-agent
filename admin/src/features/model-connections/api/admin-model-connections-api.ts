import { z } from 'zod'
import { queryOptions } from '@tanstack/react-query'
import { httpJson } from '@/core/http/client'
import type { PageResult } from '@/core/http/types'
import { queryKeys } from '@/lib/query-keys'
import type { AdminModelConnection, ConnectionStatus } from '../types'

const nullableString = z
  .string()
  .nullish()
  .transform((value) => value ?? null)

const credentialSchema = z.object({
  id: z.string(),
  maskedHint: nullableString,
  status: z.string(),
  createdAt: z.string().min(1),
})

const connectionSchema = z.object({
  id: z.string(),
  userId: z.string(),
  username: nullableString,
  displayName: nullableString,
  provider: z.string(),
  providerName: z.string(),
  baseUrl: z.string(),
  status: z.string(),
  lastVerifiedAt: nullableString,
  createdAt: z.string().min(1),
  credential: credentialSchema
    .nullish()
    .transform((value) => value ?? null),
})

const connectionPageSchema = z.object({
  list: z.array(connectionSchema),
  total: z.number(),
  page: z.number(),
  size: z.number(),
})

export interface AdminConnectionListParams {
  page: number
  size: number
  userId?: string
  provider?: string
  status?: ConnectionStatus | ''
}

/** 模型连接只读列表：分页与过滤全部由服务端执行。 */
export async function fetchAdminConnections(
  params: AdminConnectionListParams
): Promise<PageResult<AdminModelConnection>> {
  return connectionPageSchema.parse(
    await httpJson<unknown>({
      url: '/admin/model-connections',
      method: 'get',
      params: {
        page: params.page,
        size: params.size,
        userId: params.userId || undefined,
        provider: params.provider || undefined,
        status: params.status || undefined,
      },
    })
  )
}

export const adminConnectionsQueryOptions = (
  params: AdminConnectionListParams
) =>
  queryOptions({
    queryKey: [...queryKeys.adminConnections.all, 'list', params],
    queryFn: () => fetchAdminConnections(params),
  })
