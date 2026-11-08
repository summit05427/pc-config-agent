/** 审计事件白名单，与 Java `AdminAuditLogListQuery.EVENT_PATTERN` 保持一致。 */
export const AUDIT_EVENTS = [
  'login_success',
  'login_failure',
  'refresh_replay',
  'logout',
  'logout_all',
  'password_change',
  'user_disabled',
  'role_changed',
  'model_credential_created',
  'model_credential_verified',
  'model_credential_verify_failed',
  'model_credential_updated',
  'model_credential_deleted',
] as const

export type AuditEvent = (typeof AUDIT_EVENTS)[number]

export const AUDIT_EVENT_LABELS: Record<AuditEvent, string> = {
  login_success: '登录成功',
  login_failure: '登录失败',
  refresh_replay: '刷新令牌重放',
  logout: '退出登录',
  logout_all: '退出所有设备',
  password_change: '修改密码',
  user_disabled: '账号被禁用',
  role_changed: '角色变更',
  model_credential_created: '创建模型密钥',
  model_credential_verified: '模型密钥验证通过',
  model_credential_verify_failed: '模型密钥验证失败',
  model_credential_updated: '轮换模型密钥',
  model_credential_deleted: '删除模型密钥',
}

export interface AuditLogItem {
  event: AuditEvent
  username: string
  ip: string | null
  createdAt: string
}

export function getAuditEventLabel(event: string): string {
  return AUDIT_EVENT_LABELS[event as AuditEvent] ?? event
}
