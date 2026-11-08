import { formatDateTime } from '@/lib/format'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { TableState } from '@/components/table-state'
import {
  getCostStatusLabel,
  getCredentialSourceLabel,
  getUsageResultLabel,
  type AdminUsageItem,
} from '../types'

interface UsageTableProps {
  items: AdminUsageItem[]
  isPending: boolean
  hasError: boolean
  onRetry: () => void
}

function tokenLabel(value: number | null): string {
  return value === null ? '—' : value.toLocaleString('zh-CN')
}

/** 已估算才展示金额；未知与 BYOK 不计费展示状态文案，避免把空值读成 0 元。 */
function costLabel(item: AdminUsageItem): string {
  if (item.costStatus !== 'ESTIMATED' || item.estimatedCost === null) {
    return getCostStatusLabel(item.costStatus)
  }
  const amount = item.estimatedCost.toLocaleString('zh-CN', {
    maximumFractionDigits: 6,
  })
  return `${item.currency ?? ''} ${amount}`.trim()
}

export function UsageTable({
  items,
  isPending,
  hasError,
  onRetry,
}: UsageTableProps) {
  if (isPending) {
    return <TableState kind='loading' description='正在获取用量明细…' />
  }

  if (hasError) {
    return (
      <TableState
        kind='error'
        title='用量明细加载失败'
        description='请稍后重试，或点击下方按钮重新加载。'
        onRetry={onRetry}
      />
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>发生时间</TableHead>
          <TableHead>用户</TableHead>
          <TableHead>Provider / 模型</TableHead>
          <TableHead>凭证来源</TableHead>
          <TableHead>Token（入 / 出）</TableHead>
          <TableHead>延迟</TableHead>
          <TableHead>结果</TableHead>
          <TableHead>成本</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => (
          <TableRow key={item.invocationId}>
            <TableCell className='text-xs whitespace-nowrap'>
              {formatDateTime(item.occurredAt)}
            </TableCell>
            <TableCell>
              <p className='font-medium'>{item.username}</p>
              <p className='text-xs text-muted-foreground'>{item.userId}</p>
            </TableCell>
            <TableCell>
              <p className='font-medium'>{item.provider}</p>
              <p className='text-xs text-muted-foreground'>{item.modelKey}</p>
            </TableCell>
            <TableCell>
              {getCredentialSourceLabel(item.credentialSource)}
            </TableCell>
            <TableCell className='text-xs'>
              {tokenLabel(item.promptTokens)} /{' '}
              {tokenLabel(item.completionTokens)}
            </TableCell>
            <TableCell className='text-xs'>
              {item.latencyMs === null ? '—' : `${item.latencyMs} ms`}
            </TableCell>
            <TableCell>
              <Badge
                variant={
                  item.status === 'success' ? 'secondary' : 'destructive'
                }
              >
                {getUsageResultLabel(item.status)}
              </Badge>
              {item.errorType && (
                <p className='mt-1 text-xs text-muted-foreground'>
                  {item.errorType}
                </p>
              )}
            </TableCell>
            <TableCell className='text-xs'>{costLabel(item)}</TableCell>
          </TableRow>
        ))}
        {items.length === 0 && (
          <TableState
            kind='empty'
            colSpan={8}
            title='没有符合条件的用量记录'
            description='调整时间范围、用户或结果筛选后再试。'
          />
        )}
      </TableBody>
    </Table>
  )
}
