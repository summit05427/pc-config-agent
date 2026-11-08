import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, ArchiveRestore, Trash2 } from 'lucide-react'
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

import { SettingsSection } from '../settings-section'

const ARCHIVED_PAGE_SIZE = 50

/** 已归档的聊天：支持多选后批量取消归档或批量删除 */
export function ArchivedChatsSection() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const archivedQuery = useQuery(sessionsListQueryOptions(1, ARCHIVED_PAGE_SIZE, true))
  const sessions = archivedQuery.data?.list ?? []
  const selection = useSessionSelection(sessions)
  const [isDeleteOpen, setIsDeleteOpen] = useState(false)

  const restoreMutation = useMutation({
    mutationFn: (threadIds: readonly string[]) => setSessionsArchived(threadIds, false),
    onSuccess: async (result) => {
      if (result.succeeded.length > 0) {
        toast.success(t('settings.chats.batchRestoreSuccess', { count: result.succeeded.length }))
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
  const isBatchPending = restoreMutation.isPending || deleteMutation.isPending

  return (
    <SettingsSection
      title={t('settings.sections.archivedChats')}
      description={t('settings.sectionHints.archivedChats')}
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3 rounded-[var(--cds-panel-radius)] border border-dashed border-border px-4 py-3">
          <Archive className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <p className="min-w-0 flex-1 text-xs text-muted-foreground">
            {t('settings.chats.archivedCountValue', { count: archivedQuery.data?.total ?? 0 })}
          </p>
        </div>

        <SelectableSessionList
          sessions={sessions}
          isLoading={archivedQuery.isLoading}
          errorMessage={archivedQuery.isError ? t('common.loadFailed') : undefined}
          emptyMessageKey="settings.chats.archivedEmpty"
          selectedIds={selection.selectedIds}
          onToggle={selection.toggle}
          onToggleAll={selection.toggleAll}
          onOpen={(threadId) =>
            void navigate({ to: '/chat/$sessionId', params: { sessionId: threadId } })
          }
          onRetry={() => void archivedQuery.refetch()}
          actions={
            <>
              <Button
                variant="outline"
                size="sm"
                disabled={selectedThreadIds.length === 0 || isBatchPending}
                onClick={() => restoreMutation.mutate(selectedThreadIds)}
              >
                <ArchiveRestore className="size-3.5" />
                {t('settings.chats.batchRestore')}
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

        <p className="text-xs leading-relaxed text-muted-foreground">
          {t('settings.chats.archivedHint')}
        </p>
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
