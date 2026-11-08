import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import {
  deleteSessions,
  sessionsListQueryOptions,
  setSessionsArchived,
} from '@/features/sessions/api'
import { SelectableSessionList } from '@/features/sessions/components/selectable-session-list'
import { useSessionSelection } from '@/features/sessions/lib/use-session-selection'
import { queryKeys } from '@/shared/lib/query-keys'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/shared/ui/alert-dialog'
import { Button } from '@/shared/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/shared/ui/select'

import { useSettingsDraftStore, type RetentionPeriod } from '../../model/settings-draft'
import { SettingsField } from '../settings-field'
import { SettingsSection } from '../settings-section'
import { SettingsToggleRow } from '../settings-toggle-row'

const RETENTION_OPTIONS = [
  { value: 'forever', labelKey: 'settings.chats.retentionForever' },
  { value: '90', labelKey: 'settings.chats.retention90' },
  { value: '30', labelKey: 'settings.chats.retention30' },
] as const

const CHATS_PAGE_SIZE = 50

/** 聊天与数据：可多选的历史会话列表，支持批量归档与删除 */
export function ChatsSection() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const chatsQuery = useQuery(sessionsListQueryOptions(1, CHATS_PAGE_SIZE))
  const sessions = chatsQuery.data?.list ?? []
  const selection = useSessionSelection(sessions)
  const [isDeleteOpen, setIsDeleteOpen] = useState(false)
  const chats = useSettingsDraftStore((state) => state.chats)
  const updateChats = useSettingsDraftStore((state) => state.updateChats)

  const archiveMutation = useMutation({
    mutationFn: (threadIds: readonly string[]) => setSessionsArchived(threadIds, true),
    onSuccess: async (result) => {
      if (result.succeeded.length > 0) {
        toast.success(
          t('settings.chats.batchArchiveSuccess', { count: result.succeeded.length }),
        )
      }
      if (result.failed.length > 0) {
        toast.error(t('settings.chats.batchPartialFailure', { count: result.failed.length }))
      }
      selection.clear()
      await queryClient.invalidateQueries({ queryKey: queryKeys.sessions.lists })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (threadIds: readonly string[]) => deleteSessions(threadIds),
    onSuccess: async (result) => {
      if (result.succeeded.length > 0) {
        toast.success(t('settings.chats.batchDeleteSuccess', { count: result.succeeded.length }))
      }
      if (result.failed.length > 0) {
        toast.error(t('settings.chats.batchPartialFailure', { count: result.failed.length }))
      }
      setIsDeleteOpen(false)
      selection.clear()
      await queryClient.invalidateQueries({ queryKey: queryKeys.sessions.lists })
    },
  })

  const selectedThreadIds = [...selection.selectedIds]
  const isBatchPending = archiveMutation.isPending || deleteMutation.isPending

  return (
    <SettingsSection
      title={t('settings.sections.chats')}
      description={t('settings.sectionHints.chats')}
    >
      <div className="flex flex-col gap-4">
        <div>
          <h3 className="text-sm font-medium text-foreground">
            {t('settings.chats.listTitle')}
          </h3>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            {t('settings.chats.listHint')}
          </p>
        </div>

        <SelectableSessionList
          sessions={sessions}
          isLoading={chatsQuery.isLoading}
          errorMessage={chatsQuery.isError ? t('common.loadFailed') : undefined}
          emptyMessageKey="settings.chats.listEmpty"
          selectedIds={selection.selectedIds}
          onToggle={selection.toggle}
          onToggleAll={selection.toggleAll}
          onOpen={(threadId) =>
            void navigate({ to: '/chat/$sessionId', params: { sessionId: threadId } })
          }
          onRetry={() => void chatsQuery.refetch()}
          actions={
            <>
              <Button
                variant="outline"
                size="sm"
                disabled={selectedThreadIds.length === 0 || isBatchPending}
                onClick={() => archiveMutation.mutate(selectedThreadIds)}
              >
                <Archive className="size-3.5" />
                {t('settings.chats.batchArchive')}
              </Button>
              <Button
                variant="destructive"
                size="sm"
                disabled={selectedThreadIds.length === 0 || isBatchPending}
                onClick={() => setIsDeleteOpen(true)}
              >
                <Trash2 className="size-3.5" />
                {t('settings.chats.batchDelete')}
              </Button>
            </>
          }
        />
      </div>

      <div className="flex flex-col gap-5 border-t border-border pt-6">
        <h3 className="text-sm font-medium text-foreground">
          {t('settings.chats.retentionTitle')}
        </h3>

        <SettingsField id="settings-chats-retention" label={t('settings.chats.retention')}>
          <Select
            value={chats.retention}
            onValueChange={(value) => updateChats({ retention: value as RetentionPeriod })}
          >
            <SelectTrigger id="settings-chats-retention" size="sm" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent position="popper">
              {RETENTION_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {t(option.labelKey)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </SettingsField>

        <SettingsToggleRow
          id="settings-chats-auto-archive"
          label={t('settings.chats.autoArchive')}
          description={t('settings.chats.autoArchiveHint')}
          checked={chats.autoArchive}
          onCheckedChange={(autoArchive) => updateChats({ autoArchive })}
        />
      </div>

      <AlertDialog open={isDeleteOpen} onOpenChange={setIsDeleteOpen}>
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('settings.chats.batchDeleteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('settings.chats.batchDeleteDescription', { count: selectedThreadIds.length })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMutation.isPending}>
              {t('common.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={deleteMutation.isPending}
              onClick={(event) => {
                // 成功后再由 onSuccess 关闭弹窗，失败时保留供用户重试
                event.preventDefault()
                deleteMutation.mutate(selectedThreadIds)
              }}
            >
              {deleteMutation.isPending ? t('common.deleting') : t('settings.chats.batchDelete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </SettingsSection>
  )
}
