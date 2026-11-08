/** 与 Java `AdminUserSummaryResponse` 对齐的账号状态枚举。 */
export const USER_STATUSES = ['ACTIVE', 'DISABLED'] as const
export type UserStatus = (typeof USER_STATUSES)[number]

/** 业务角色，不带 Spring Security 的 ROLE_ 前缀。 */
export const USER_ROLES = ['USER', 'ADMIN'] as const
export type UserRole = (typeof USER_ROLES)[number]

export interface AdminUserSummary {
  publicId: string
  username: string
  email: string | null
  roles: string[]
  status: UserStatus
  createdAt: string
}

export const USER_STATUS_LABELS: Record<UserStatus, string> = {
  ACTIVE: '启用',
  DISABLED: '禁用',
}
