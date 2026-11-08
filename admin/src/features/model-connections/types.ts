/**
 * 管理端模型连接展示类型，字段与 `/api/v1/admin/model-connections` 响应保持一致。
 *
 * 凭证只有掩码与状态，任何情况下都不包含密文或明文。
 */
export interface AdminConnectionCredential {
  id: string
  maskedHint: string | null
  status: string
  createdAt: string
}

export interface AdminModelConnection {
  id: string
  userId: string
  username: string | null
  displayName: string | null
  provider: string
  providerName: string
  baseUrl: string
  status: string
  lastVerifiedAt: string | null
  createdAt: string
  credential: AdminConnectionCredential | null
}

export const CONNECTION_STATUSES = ['ACTIVE', 'DELETED'] as const
export type ConnectionStatus = (typeof CONNECTION_STATUSES)[number]

export const CONNECTION_STATUS_LABELS: Record<string, string> = {
  ACTIVE: '有效',
  DELETED: '已删除',
}

/** 凭证状态是协议字段，展示文案在本地映射。 */
export const CREDENTIAL_STATUS_LABELS: Record<string, string> = {
  UNVERIFIED: '未验证',
  VERIFIED: '已验证',
  REVOKED: '已撤销',
}

export function getConnectionStatusLabel(value: string): string {
  return CONNECTION_STATUS_LABELS[value] ?? value
}

export function getCredentialStatusLabel(value: string): string {
  return CREDENTIAL_STATUS_LABELS[value] ?? value
}
