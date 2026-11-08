import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { revokeDeviceSession, type DeviceSessionSummary } from '@/features/auth/api'
import { deviceSessionsQueryOptions } from '@/features/settings/api'
import { queryKeys } from '@/shared/lib/query-keys'
import { formatDateTime } from '@/shared/lib/format'
import { Button } from '@/shared/ui/button'
import { Badge } from '@/shared/ui/badge'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/shared/ui/alert-dialog'

interface SessionRowProps {
  session: DeviceSessionSummary
  isRevoking: boolean
  onRevoke: (familyId: string) => void
}

function SessionRow({ session, isRevoking, onRevoke }: SessionRowProps) {
  const { t } = useTranslation()

  return (
    <li className="flex items-center justify-between gap-4 px-4 py-3">
      <div className="min-w-0">
        <p className="flex items-center gap-2 text-sm font-medium text-foreground">
          <span className="truncate">{formatDateTime(session.createdAt)}</span>
          {session.current ? (
            <Badge variant="secondary">{t('settings.security.currentDevice')}</Badge>
          ) : null}
        </p>
        <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
          {t('settings.security.lastActive')}:{' '}
          {session.lastUsedAt
            ? formatDateTime(session.lastUsedAt)
            : t('settings.security.neverUsed')}{' '}
          · {t('settings.security.expiresAt')}: {formatDateTime(session.absoluteExpiresAt)}
        </p>
      </div>

      {session.current ? (
        <span className="shrink-0 text-xs text-muted-foreground">
          {t('settings.security.currentDeviceHint')}
        </span>
      ) : (
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="outline" size="sm" className="shrink-0" disabled={isRevoking}>
              {isRevoking ? t('settings.security.revoking') : t('settings.security.revokeDevice')}
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('settings.security.revokeDevice')}</AlertDialogTitle>
              <AlertDialogDescription>
                {t('settings.security.revokeConfirm')}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
              <AlertDialogAction variant="destructive" onClick={() => onRevoke(session.familyId)}>
                {t('settings.security.revokeDevice')}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
    </li>
  )
}

/** 登录设备：一次取满后端上限，列表固定高度、超出滚动；撤销其他设备需二次确认 */
export function DeviceSessions() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const sessionsQuery = useQuery(deviceSessionsQueryOptions())
  const revokeMutation = useMutation({ mutationFn: revokeDeviceSession })

  const sessions = sessionsQuery.data?.list ?? []

  const revoke = async (familyId: string): Promise<void> => {
    try {
      await revokeMutation.mutateAsync(familyId)
      await queryClient.invalidateQueries({ queryKey: queryKeys.settings.deviceSessionsAll })
      toast.success(t('settings.security.sessionRevoked'))
    } catch {
      // 请求层已提示服务端错误，这里只保持当前列表不变
    }
  }

  return (
    <div className="flex flex-col gap-4 border-t border-border pt-6">
      <div>
        <h3 className="text-sm font-medium text-foreground">
          {t('settings.security.sessionsTitle')}
        </h3>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          {t('settings.security.sessionsHint')}
        </p>
      </div>

      {sessionsQuery.isLoading && sessions.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t('settings.security.sessionsLoading')}</p>
      ) : null}

      {sessionsQuery.isError ? (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-3 rounded-[var(--cds-panel-radius)] border border-dashed border-border px-4 py-4"
        >
          <p className="min-w-0 flex-1 text-xs text-muted-foreground">{t('common.loadFailed')}</p>
          <Button variant="outline" size="sm" onClick={() => void sessionsQuery.refetch()}>
            {t('common.retry')}
          </Button>
        </div>
      ) : null}

      {!sessionsQuery.isLoading && !sessionsQuery.isError && sessions.length === 0 ? (
        <p className="rounded-[var(--cds-panel-radius)] border border-dashed border-border px-4 py-8 text-center text-xs text-muted-foreground">
          {t('settings.security.sessionsEmpty')}
        </p>
      ) : null}

      {/* 列表行左对齐且有边框，只预留右侧槽位：滚动条出现时行宽不变，也不会在边框内侧多出空隙 */}
      {sessions.length > 0 ? (
        <ul className="max-h-80 divide-y divide-border overflow-y-auto [scrollbar-gutter:stable] rounded-[var(--cds-panel-radius)] border border-border">
          {sessions.map((session) => (
            <SessionRow
              key={session.familyId}
              session={session}
              isRevoking={revokeMutation.isPending && revokeMutation.variables === session.familyId}
              onRevoke={(familyId) => void revoke(familyId)}
            />
          ))}
        </ul>
      ) : null}
    </div>
  )
}
