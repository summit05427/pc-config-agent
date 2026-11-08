import { AlertCircle, Loader2, PackageOpen, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { TableCell, TableRow } from '@/components/ui/table'

type TableStateKind = 'loading' | 'error' | 'empty'

interface TableStateProps {
  kind: TableStateKind
  /** 传入时渲染为表格行（空态用），否则渲染为块级占位（loading / error 用）。 */
  colSpan?: number
  title?: string
  description?: string
  onRetry?: () => void
}

const STATE_ICONS = {
  loading: Loader2,
  error: AlertCircle,
  empty: PackageOpen,
} as const

const DEFAULT_TITLES: Record<TableStateKind, string> = {
  loading: '加载中…',
  error: '数据加载失败',
  empty: '暂无数据',
}

/**
 * 表格三态统一占位：加载、错误、空数据。
 *
 * 错误态提供重试入口，避免用户只能刷新整页；空态保留表头，
 * 让用户仍能确认当前列结构与筛选条件。
 */
export function TableState({
  kind,
  colSpan,
  title,
  description,
  onRetry,
}: TableStateProps) {
  const Icon = STATE_ICONS[kind]

  const content = (
    <div
      className='flex flex-col items-center gap-2 py-8 text-center'
      role={
        kind === 'error' ? 'alert' : kind === 'loading' ? 'status' : undefined
      }
    >
      <Icon
        aria-hidden='true'
        className={cn(
          'size-6 text-muted-foreground',
          kind === 'loading' && 'animate-spin',
          kind === 'error' && 'text-destructive'
        )}
      />
      <p
        className={cn(
          'text-sm font-medium',
          kind === 'error' && 'text-destructive'
        )}
      >
        {title ?? DEFAULT_TITLES[kind]}
      </p>
      {description && (
        <p className='text-sm text-muted-foreground'>{description}</p>
      )}
      {kind === 'error' && onRetry && (
        <Button variant='outline' size='sm' onClick={onRetry}>
          <RefreshCw className='size-4' />
          重试
        </Button>
      )}
    </div>
  )

  if (colSpan !== undefined) {
    return (
      <TableRow>
        <TableCell colSpan={colSpan}>{content}</TableCell>
      </TableRow>
    )
  }

  return content
}
