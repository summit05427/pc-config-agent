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
  getConnectionStatusLabel,
  getCredentialStatusLabel,
  type AdminModelConnection,
} from '../types'

interface ConnectionsTableProps {
  connections: AdminModelConnection[]
  isPending: boolean
  hasError: boolean
  onRetry: () => void
}

/** 用户展示名优先；为空时退回登录名与公开 ID，保证任何一行都能定位到人。 */
function userLabel(connection: AdminModelConnection): string {
  return connection.displayName || connection.username || connection.userId
}

export function ConnectionsTable({
  connections,
  isPending,
  hasError,
  onRetry,
}: ConnectionsTableProps) {
  if (isPending) {
    return <TableState kind='loading' description='正在获取模型连接…' />
  }

  if (hasError) {
    return (
      <TableState
        kind='error'
        title='模型连接加载失败'
        description='请稍后重试，或点击下方按钮重新加载。'
        onRetry={onRetry}
      />
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>用户</TableHead>
          <TableHead>Provider</TableHead>
          <TableHead>接入地址</TableHead>
          <TableHead>连接状态</TableHead>
          <TableHead>最近验证</TableHead>
          <TableHead>当前凭证</TableHead>
          <TableHead>创建时间</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {connections.map((connection) => (
          <TableRow key={connection.id}>
            <TableCell>
              <p className='font-medium'>{userLabel(connection)}</p>
              <p className='text-xs text-muted-foreground'>
                {connection.userId}
              </p>
            </TableCell>
            <TableCell>
              <p className='font-medium'>{connection.providerName}</p>
              <p className='text-xs text-muted-foreground'>
                {connection.provider}
              </p>
            </TableCell>
            <TableCell className='max-w-64 truncate text-xs'>
              {connection.baseUrl}
            </TableCell>
            <TableCell>
              <Badge
                variant={
                  connection.status === 'ACTIVE' ? 'secondary' : 'outline'
                }
              >
                {getConnectionStatusLabel(connection.status)}
              </Badge>
            </TableCell>
            <TableCell className='text-xs whitespace-nowrap'>
              {connection.lastVerifiedAt
                ? formatDateTime(connection.lastVerifiedAt)
                : '—'}
            </TableCell>
            <TableCell>
              {connection.credential ? (
                <>
                  <p className='font-mono text-xs'>
                    {connection.credential.maskedHint ?? '—'}
                  </p>
                  <p className='text-xs text-muted-foreground'>
                    {getCredentialStatusLabel(connection.credential.status)}
                  </p>
                </>
              ) : (
                <span className='text-xs text-muted-foreground'>
                  无有效凭证
                </span>
              )}
            </TableCell>
            <TableCell className='text-xs whitespace-nowrap'>
              {formatDateTime(connection.createdAt)}
            </TableCell>
          </TableRow>
        ))}
        {connections.length === 0 && (
          <TableState
            kind='empty'
            colSpan={7}
            title='没有符合条件的模型连接'
            description='调整用户 ID、Provider 或连接状态后再试。'
          />
        )}
      </TableBody>
    </Table>
  )
}
