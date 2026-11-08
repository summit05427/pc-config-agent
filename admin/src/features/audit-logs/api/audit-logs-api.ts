import { z } from 'zod'
import { queryOptions } from '@tanstack/react-query'
import { httpJson } from '@/core/http/client'
import type { PageResult } from '@/core/http/types'
import { queryKeys } from '@/lib/query-keys'
import { AUDIT_EVENTS, type AuditLogItem } from '../types'

const auditLogSchema = z.object({
  event: z.enum(AUDIT_EVENTS),
  username: z.string(),
  ip: z
    .string()
    .nullish()
    .transform((value) => value ?? null),
  createdAt: z.string().min(1),
})

const auditLogPageSchema = z.object({
  list: z.array(auditLogSchema),
  total: z.number(),
  page: z.number(),
  size: z.number(),
})

export interface AuditLogListParams {
  page: number
  size: number
  event?: string
  username?: string
}

/** 审计日志列表：按事件与用户名精确过滤，时间倒序由服务端保证。 */
export async function fetchAuditLogs(
  params: AuditLogListParams
): Promise<PageResult<AuditLogItem>> {
  return auditLogPageSchema.parse(
    await httpJson<unknown>({
      url: '/admin/audit-logs',
      method: 'get',
      params: {
        page: params.page,
        size: params.size,
        event: params.event || undefined,
        username: params.username || undefined,
      },
    })
  )
}

export const auditLogsQueryOptions = (params: AuditLogListParams) =>
  queryOptions({
    queryKey: [...queryKeys.auditLogs.all, 'list', params],
    queryFn: () => fetchAuditLogs(params),
  })
