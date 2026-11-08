import { formatDateTime } from '@/lib/format'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
  USER_STATUS_LABELS,
  type AdminUserSummary,
} from '@/features/admin-users/types'

interface UsersTableProps {
  users: AdminUserSummary[]
  isPending: boolean
  hasError: boolean
  onRetry: () => void
  isStatusUpdating: boolean
  onEditRoles: (user: AdminUserSummary) => void
  onToggleStatus: (user: AdminUserSummary) => void
}

export function UsersTable({
  users,
  isPending,
  hasError,
  onRetry,
  isStatusUpdating,
  onEditRoles,
  onToggleStatus,
}: UsersTableProps) {
  if (isPending) {
    return <TableState kind='loading' description='正在获取用户列表…' />
  }

  if (hasError) {
    return (
      <TableState
        kind='error'
        title='用户列表加载失败'
        description='请稍后重试，或点击下方按钮重新加载。'
        onRetry={onRetry}
      />
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>用户名</TableHead>
          <TableHead>邮箱</TableHead>
          <TableHead>角色</TableHead>
          <TableHead>状态</TableHead>
          <TableHead>注册时间</TableHead>
          <TableHead className='text-end'>操作</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {users.map((user) => (
          <TableRow key={user.publicId}>
            <TableCell className='font-medium'>{user.username}</TableCell>
            <TableCell>{user.email ?? '—'}</TableCell>
            <TableCell>{user.roles.join(' / ')}</TableCell>
            <TableCell>
              <Badge
                variant={user.status === 'ACTIVE' ? 'secondary' : 'outline'}
              >
                {USER_STATUS_LABELS[user.status]}
              </Badge>
            </TableCell>
            <TableCell>{formatDateTime(user.createdAt)}</TableCell>
            <TableCell className='text-end'>
              <div className='flex justify-end gap-2'>
                <Button
                  variant='outline'
                  size='sm'
                  onClick={() => onEditRoles(user)}
                >
                  角色
                </Button>
                <Button
                  variant={user.status === 'ACTIVE' ? 'outline' : 'default'}
                  size='sm'
                  disabled={isStatusUpdating}
                  onClick={() => onToggleStatus(user)}
                >
                  {user.status === 'ACTIVE' ? '禁用' : '启用'}
                </Button>
              </div>
            </TableCell>
          </TableRow>
        ))}
        {users.length === 0 && (
          <TableState
            kind='empty'
            colSpan={6}
            title='没有符合条件的用户'
            description='调整关键字或状态筛选后再试。'
          />
        )}
      </TableBody>
    </Table>
  )
}
