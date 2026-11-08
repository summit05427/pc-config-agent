import { useTranslation } from 'react-i18next'

import type { ModelConnection } from '@/features/models/api'
import { cn } from '@/shared/lib/utils'
import { Badge } from '@/shared/ui/badge'

/** 凭证状态到词条 key；未知状态直接回退服务端原值，避免展示成空白 */
const STATUS_LABELS: Record<string, string> = {
  ACTIVE: 'settings.model.statusActive',
  UNVERIFIED: 'settings.model.statusUnverified',
  VERIFIED: 'settings.model.statusVerified',
  REVOKED: 'settings.model.statusRevoked',
}

const STATUS_DOTS: Record<string, string> = {
  ACTIVE: 'bg-success',
  UNVERIFIED: 'bg-muted-foreground/55',
  VERIFIED: 'bg-success',
  REVOKED: 'bg-destructive/70',
}

/** 已接入且可用的状态使用绿色标签，其余状态保持中性或警示色 */
const CONNECTED_STATUSES = new Set(['ACTIVE', 'VERIFIED'])

export interface ModelConnectionStatusProps {
  /** 凭证状态优先于连接状态，凭证缺失时回落到连接状态 */
  connection: Pick<ModelConnection, 'status' | 'credential'>
}

/** 连接状态徽标：列表行与详情头部共用同一套状态语义与圆点 */
export function ModelConnectionStatus({ connection }: ModelConnectionStatusProps) {
  const { t } = useTranslation()
  const status = connection.credential?.status ?? connection.status
  const labelKey = STATUS_LABELS[status]

  return (
    <Badge
      variant="outline"
      className={cn(
        'gap-1.5',
        CONNECTED_STATUSES.has(status) && 'border-success/40 bg-success/10 text-success',
      )}
    >
      <span
        aria-hidden="true"
        className={cn('size-1.5 rounded-full', STATUS_DOTS[status] ?? 'bg-muted-foreground/55')}
      />
      {labelKey ? t(labelKey) : status}
    </Badge>
  )
}
