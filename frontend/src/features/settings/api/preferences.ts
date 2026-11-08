import { http } from '@/core/http'

/** 回复语言，与 Java `user_preferences.reply_language` 取值一致 */
export type PreferenceReplyLanguage = 'auto' | 'zh-CN' | 'en-US'

/** 回复风格，与 Java `user_preferences.response_style` 取值一致 */
export type PreferenceResponseStyle = 'concise' | 'balanced' | 'detailed'

/**
 * 服务端保存的偏好。
 *
 * `updatedAt` 为 `null` 表示从未保存过，其余字段是服务端默认值而不是用户选择。
 */
export interface UserPreferences {
  instructions: string | null
  replyLanguage: PreferenceReplyLanguage
  responseStyle: PreferenceResponseStyle
  useHistory: boolean
  updatedAt: string | null
}

/** 偏好更新入参；全量提交，`instructions` 传 `null` 表示清空 */
export interface PreferenceUpdatePayload {
  instructions: string | null
  replyLanguage: PreferenceReplyLanguage
  responseStyle: PreferenceResponseStyle
  useHistory: boolean
}

/** 读取当前用户偏好；从未保存过时返回服务端默认值（`updatedAt` 为 null） */
export const getPreferences = (): Promise<UserPreferences> =>
  http.get<UserPreferences>('/users/me/preferences')

/** 保存偏好后立即回读服务端值，避免把本地草稿当作事实来源 */
export const updatePreferences = (payload: PreferenceUpdatePayload): Promise<UserPreferences> =>
  http.put<UserPreferences>('/users/me/preferences', payload)
