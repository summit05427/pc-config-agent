import { http } from '@/core/http'
import type { PageResult } from '@/shared/types/http'

/**
 * 个人资料响应。
 *
 * 只包含可对外展示的字段；内部主键与口令摘要不在任何响应中出现。
 * `displayName` / `email` / `bio` 为 `null` 表示尚未设置。
 */
export interface UserProfile {
  publicId: string
  username: string
  displayName: string | null
  email: string | null
  bio: string | null
  roles: string[]
  status: string
  createdAt: string
  updatedAt: string
}

/** 资料更新入参；`email` / `bio` 传 `null` 表示清空 */
export interface ProfileUpdatePayload {
  displayName: string
  email: string | null
  bio: string | null
}

export interface PasswordChangePayload {
  currentPassword: string
  newPassword: string
}

/** 一台登录设备 = 一个刷新令牌族 */
export interface DeviceSessionSummary {
  familyId: string
  createdAt: string
  lastUsedAt: string | null
  idleExpiresAt: string
  absoluteExpiresAt: string
  /** 仅用于展示：由访问令牌的 sid 与服务端族 ID 比对得出，不参与鉴权 */
  current: boolean
}

export interface DeviceSessionQuery {
  page: number
  size: number
}

export const getProfile = (): Promise<UserProfile> => http.get<UserProfile>('/users/me/profile')

/** 保存资料后立即回读服务端值，避免用本地草稿当事实来源 */
export const updateProfile = (payload: ProfileUpdatePayload): Promise<UserProfile> =>
  http.put<UserProfile>('/users/me/profile', payload)

/**
 * 修改密码。
 *
 * 失败（当前口令错误、新旧相同）返回 400 而不是 401，因此不会触发刷新与全局登出。
 */
export const changePassword = (payload: PasswordChangePayload): Promise<void> =>
  http.put<void>('/users/me/password', payload)

export const listDeviceSessions = (
  query: DeviceSessionQuery,
): Promise<PageResult<DeviceSessionSummary>> =>
  http.get<PageResult<DeviceSessionSummary>>('/users/me/sessions', { params: query })

/** 撤销指定设备；当前设备不允许撤销，服务端返回 409 */
export const revokeDeviceSession = (familyId: string): Promise<void> =>
  http.delete<void>(`/users/me/sessions/${encodeURIComponent(familyId)}`)
