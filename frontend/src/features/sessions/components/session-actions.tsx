import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Archive, ArchiveRestore, MoreHorizontal, Pencil, Pin, PinOff, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

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
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/shared/ui/dropdown-menu'
import { Input } from '@/shared/ui/input'

import { deleteSession, renameSession, setSessionArchived, setSessionPinned } from '../api'
import type { SessionSummary } from '../api/types'
import { sortSessionSummaries, updateCachedSessionLists } from '../lib/session-cache'

/** 与服务端 PATCH 契约一致：标题去掉首尾空白后最多 80 字符 */
const RENAME_MAX_LENGTH = 80

export interface SessionActionsProps {
  readonly session: SessionSummary
  /** 删除成功后由父级决定是否离开当前会话；重命名不需要父级介入 */
  readonly onDeleted?: (threadId: string) => void
  /** 归档成功后由父级决定是否离开当前会话 */
  readonly onArchived?: (threadId: string) => void
}

/**
 * 会话行的「⋯」菜单与两个确认弹窗。
 *
 * 置顶、归档、重命名与删除都调用真实接口，成功后统一失效会话列表；
 * 菜单按当前状态给出反向操作：已置顶显示「取消置顶」，已归档显示「取消归档」。
 */
export function SessionActions({ session, onDeleted, onArchived }: SessionActionsProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const renameInputId = useId()
  const [isRenameOpen, setIsRenameOpen] = useState(false)
  const [isDeleteOpen, setIsDeleteOpen] = useState(false)
  const [renameDraft, setRenameDraft] = useState('')

  const currentTitle = session.title?.trim() ?? ''

  const renameMutation = useMutation({
    mutationFn: (title: string) => renameSession(session.thread_id, title),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.sessions.all })
      setIsRenameOpen(false)
      toast.success(t('chat.sessions.renameSuccess'))
    },
    onError: () => toast.error(t('chat.sessions.actionFailed')),
  })

  // 置顶/归档先改本地缓存再等接口确认：本地请求再快也有往返，
  // 没有乐观更新时用户点完看不到任何变化，会误以为按钮失效。
  const pinMutation = useMutation({
    mutationFn: (pinned: boolean) => setSessionPinned(session.thread_id, pinned),
    onMutate: async (pinned) => {
      // 先停掉在途刷新，避免旧响应把乐观结果覆盖回未置顶状态
      await queryClient.cancelQueries({ queryKey: queryKeys.sessions.lists })
      updateCachedSessionLists(queryClient, (list) =>
        sortSessionSummaries(
          list.map((item) =>
            item.thread_id === session.thread_id ? { ...item, is_pinned: pinned } : item,
          ),
        ),
      )
    },
    onError: () => {
      // 回滚方式统一为重新拉取，避免手写反向补丁与并发操作互相覆盖
      void queryClient.invalidateQueries({ queryKey: queryKeys.sessions.lists })
      toast.error(t('chat.sessions.actionFailed'))
    },
    onSuccess: async (_result, pinned) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.sessions.lists })
      toast.success(
        pinned ? t('chat.sessions.pinSuccess') : t('chat.sessions.unpinSuccess'),
      )
    },
  })

  const archiveMutation = useMutation({
    mutationFn: (archived: boolean) => setSessionArchived(session.thread_id, archived),
    onMutate: async (archived) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.sessions.lists })
      updateCachedSessionLists(queryClient, (list) =>
        archived
          ? list.filter((item) => item.thread_id !== session.thread_id)
          : list.map((item) =>
              item.thread_id === session.thread_id ? { ...item, is_archived: false } : item,
            ),
      )
    },
    onError: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.sessions.lists })
      toast.error(t('chat.sessions.actionFailed'))
    },
    onSuccess: async (_result, archived) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.sessions.lists })
      toast.success(
        archived ? t('chat.sessions.archiveSuccess') : t('chat.sessions.unarchiveSuccess'),
      )
      if (archived) {
        onArchived?.(session.thread_id)
      }
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteSession(session.thread_id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.sessions.all })
      setIsDeleteOpen(false)
      toast.success(t('chat.sessions.deleteSuccess'))
      onDeleted?.(session.thread_id)
    },
    onError: () => toast.error(t('chat.sessions.actionFailed')),
  })

  // 每次打开都回填服务端当前标题，避免上次编辑残留覆盖真实值
  const handleRenameOpenChange = (open: boolean): void => {
    setIsRenameOpen(open)
    if (open) {
      setRenameDraft(currentTitle)
    }
  }

  const handleRenameSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault()
    const title = renameDraft.trim()
    if (!title || renameMutation.isPending) {
      return
    }
    renameMutation.mutate(title)
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label={t('chat.sessions.more')}
            className="mr-1 shrink-0 text-muted-foreground"
          >
            <MoreHorizontal className="size-3.5" />
          </Button>
        </DropdownMenuTrigger>

        <DropdownMenuContent align="end" className="w-44">
          <DropdownMenuItem onSelect={() => handleRenameOpenChange(true)}>
            <Pencil aria-hidden="true" />
            {t('chat.sessions.rename')}
          </DropdownMenuItem>
          {session.is_pinned ? (
            <DropdownMenuItem
              disabled={pinMutation.isPending}
              onSelect={() => pinMutation.mutate(false)}
            >
              <PinOff aria-hidden="true" />
              {t('chat.sessions.unpin')}
            </DropdownMenuItem>
          ) : (
            <DropdownMenuItem
              disabled={pinMutation.isPending}
              onSelect={() => pinMutation.mutate(true)}
            >
              <Pin aria-hidden="true" />
              {t('chat.sessions.pin')}
            </DropdownMenuItem>
          )}
          <DropdownMenuItem
            disabled={archiveMutation.isPending}
            onSelect={() => archiveMutation.mutate(!session.is_archived)}
          >
            {session.is_archived ? (
              <ArchiveRestore aria-hidden="true" />
            ) : (
              <Archive aria-hidden="true" />
            )}
            {session.is_archived ? t('chat.sessions.unarchive') : t('chat.sessions.archive')}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem variant="destructive" onSelect={() => setIsDeleteOpen(true)}>
            <Trash2 aria-hidden="true" />
            {t('chat.sessions.delete')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={isRenameOpen} onOpenChange={handleRenameOpenChange}>
        <DialogContent className="sm:max-w-[24rem]">
          <DialogHeader>
            <DialogTitle>{t('chat.sessions.renameTitle')}</DialogTitle>
            <DialogDescription>{t('chat.sessions.renameHint')}</DialogDescription>
          </DialogHeader>

          <form className="flex flex-col gap-2" onSubmit={handleRenameSubmit}>
            <label className="text-xs font-medium text-muted-foreground" htmlFor={renameInputId}>
              {t('chat.sessions.titleLabel')}
            </label>
            <Input
              id={renameInputId}
              value={renameDraft}
              maxLength={RENAME_MAX_LENGTH}
              autoFocus
              placeholder={t('chat.sessions.titlePlaceholder')}
              disabled={renameMutation.isPending}
              onChange={(event) => setRenameDraft(event.target.value)}
            />

            <DialogFooter className="pt-2">
              <DialogClose asChild>
                <Button type="button" variant="outline" disabled={renameMutation.isPending}>
                  {t('common.cancel')}
                </Button>
              </DialogClose>
              <Button
                type="submit"
                disabled={!renameDraft.trim() || renameMutation.isPending}
              >
                {renameMutation.isPending ? t('common.saving') : t('common.save')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog open={isDeleteOpen} onOpenChange={setIsDeleteOpen}>
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('chat.sessions.deleteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('chat.sessions.deleteDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMutation.isPending}>
              {t('common.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={deleteMutation.isPending}
              onClick={(event) => {
                // 请求成功后再由 onSuccess 关闭，失败时保留弹窗供用户重试
                event.preventDefault()
                deleteMutation.mutate()
              }}
            >
              {deleteMutation.isPending ? t('common.deleting') : t('chat.sessions.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
