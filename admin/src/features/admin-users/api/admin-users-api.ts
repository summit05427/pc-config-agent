import { z } from 'zod'
import { queryOptions } from '@tanstack/react-query'
import { httpJson } from '@/core/http/client'
import type { PageResult } from '@/core/http/types'
import { queryKeys } from '@/lib/query-keys'
import {
  USER_STATUSES,
  type AdminUserSummary,
  type UserRole,
  type UserStatus,
} from '../types'

const adminUserSchema = z.object({
  publicId: z.string().min(1),
  username: z.string().min(1),
  email: z
    .string()
    .nullish()
    .transform((value) => value ?? null),
  roles: z.array(z.string()),
  status: z.enum(USER_STATUSES),
  createdAt: z.string().min(1),
})

const userPageSchema = z.object({
  list: z.array(adminUserSchema),
  total: z.number(),
  page: z.number(),
  size: z.number(),
})

export interface AdminUserListParams {
  page: number
  size: number
  keyword?: string
  status?: UserStatus
}

/** 管理端用户列表：分页、关键字与状态过滤全部由服务端处理。 */
export async function fetchAdminUsers(
  params: AdminUserListParams
): Promise<PageResult<AdminUserSummary>> {
  return userPageSchema.parse(
    await httpJson<unknown>({
      url: '/admin/users',
      method: 'get',
      // 空串表示不过滤，必须转成 undefined，避免服务端把空串当关键字
      params: {
        page: params.page,
        size: params.size,
        keyword: params.keyword || undefined,
        status: params.status || undefined,
      },
    })
  )
}

export const adminUsersQueryOptions = (params: AdminUserListParams) =>
  queryOptions({
    queryKey: [...queryKeys.adminUsers.all, 'list', params],
    queryFn: () => fetchAdminUsers(params),
  })

export async function updateUserStatus(
  publicId: string,
  status: UserStatus
): Promise<AdminUserSummary> {
  return adminUserSchema.parse(
    await httpJson<unknown>({
      url: `/admin/users/${encodeURIComponent(publicId)}/status`,
      method: 'patch',
      data: { status },
    })
  )
}

export async function updateUserRoles(
  publicId: string,
  roles: UserRole[]
): Promise<AdminUserSummary> {
  return adminUserSchema.parse(
    await httpJson<unknown>({
      url: `/admin/users/${encodeURIComponent(publicId)}/roles`,
      method: 'patch',
      data: { roles },
    })
  )
}
