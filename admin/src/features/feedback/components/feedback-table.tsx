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
  getRatingLabel,
  getReasonLabel,
  type AdminFeedbackItem,
} from '../types'

interface FeedbackTableProps {
  items: AdminFeedbackItem[]
  isPending: boolean
  hasError: boolean
  onRetry: () => void
}

export function FeedbackTable({
  items,
  isPending,
  hasError,
  onRetry,
}: FeedbackTableProps) {
  if (isPending) {
    return <TableState kind='loading' description='正在获取反馈明细…' />
  }

  if (hasError) {
    return (
      <TableState
        kind='error'
        title='反馈明细加载失败'
        description='请稍后重试，或点击下方按钮重新加载。'
        onRetry={onRetry}
      />
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>提交时间</TableHead>
          <TableHead>用户</TableHead>
          <TableHead>会话 / 消息</TableHead>
          <TableHead>评分</TableHead>
          <TableHead>原因</TableHead>
          <TableHead>用户备注</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => (
          <TableRow key={`${item.userId}:${item.messageId}`}>
            <TableCell className='text-xs whitespace-nowrap'>
              {formatDateTime(item.createdAt)}
            </TableCell>
            <TableCell>
              <p className='font-medium'>{item.username ?? '用户已删除'}</p>
              <p className='text-xs text-muted-foreground'>{item.userId}</p>
            </TableCell>
            <TableCell className='max-w-56'>
              <p className='truncate text-xs' title={item.threadId}>
                {item.threadId}
              </p>
              <p className='truncate text-xs text-muted-foreground' title={item.messageId}>
                {item.messageId}
              </p>
            </TableCell>
            <TableCell>
              <Badge variant={item.rating === 'UP' ? 'secondary' : 'destructive'}>
                {getRatingLabel(item.rating)}
              </Badge>
            </TableCell>
            <TableCell className='text-xs'>{getReasonLabel(item.reasonCode)}</TableCell>
            <TableCell className='max-w-72'>
              {item.comment ? (
                <p className='truncate text-xs' title={item.comment}>
                  {item.comment}
                </p>
              ) : (
                <span className='text-xs text-muted-foreground'>—</span>
              )}
            </TableCell>
          </TableRow>
        ))}
        {items.length === 0 && (
          <TableState
            kind='empty'
            colSpan={6}
            title='没有符合条件的反馈'
            description='调整评分、原因或时间范围后再试。'
          />
        )}
      </TableBody>
    </Table>
  )
}
