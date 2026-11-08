import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { toast } from 'sonner'
import { queryKeys } from '@/lib/query-keys'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { PaginationBar } from '@/components/pagination-bar'
import {
  adminUsersQueryOptions,
  updateUserRoles,
  updateUserStatus,
} from '@/features/admin-users/api/admin-users-api'
import { UserRolesDialog } from '@/features/admin-users/components/user-roles-dialog'
import { UsersTable } from '@/features/admin-users/components/users-table'
import {
  USER_STATUSES,
  USER_STATUS_LABELS,
  type AdminUserSummary,
  type UserRole,
} from '@/features/admin-users/types'

const PAGE_SIZES = [10, 20, 50, 100]

export function AdminUsersPage() {
  const search = useSearch({ from: '/_authenticated/users/' })
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [keywordInput, setKeywordInput] = useState(search.keyword)
  const [editingUser, setEditingUser] = useState<AdminUserSummary | null>(null)

  const usersQuery = useQuery(
    adminUsersQueryOptions({
      page: search.page,
      size: search.size,
      keyword: search.keyword || undefined,
      status: search.status || undefined,
    })
  )

  const statusMutation = useMutation({
    mutationFn: (user: AdminUserSummary) =>
      updateUserStatus(
        user.publicId,
        user.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE'
      ),
    onSuccess: (updatedUser) => {
      toast.success(
        `${updatedUser.username} 已${USER_STATUS_LABELS[updatedUser.status]}`
      )
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers.all })
    },
  })

  const rolesMutation = useMutation({
    mutationFn: (input: { publicId: string; roles: UserRole[] }) =>
      updateUserRoles(input.publicId, input.roles),
    onSuccess: (updatedUser) => {
      toast.success(`${updatedUser.username} 的角色已更新`)
      setEditingUser(null)
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers.all })
    },
  })

  function updateSearch(next: {
    page?: number
    size?: number
    keyword?: string
    status?: string
  }) {
    navigate({
      to: '/users',
      search: (previous) => ({
        keyword: next.keyword ?? previous.keyword ?? '',
        status: (next.status ?? previous.status) as '' | 'ACTIVE' | 'DISABLED',
        size: next.size ?? previous.size ?? 20,
        // 过滤条件变化时回到第一页，避免停留在越界页码
        page: next.page ?? 1,
      }),
    })
  }

  return (
    <>
      <Header fixed />
      <Main className='flex flex-1 flex-col gap-4 sm:gap-6'>
        <div className='flex flex-col gap-4'>
          <div>
            <h1 className='text-2xl font-bold tracking-tight'>用户管理</h1>
            <p className='text-sm text-muted-foreground'>
              查询账号状态与角色；禁用账号会同时吊销该用户全部刷新会话。
            </p>
          </div>

          <div className='flex flex-wrap items-end gap-3'>
            <div className='grid gap-1.5'>
              <Label htmlFor='keyword'>用户名或邮箱</Label>
              <Input
                id='keyword'
                value={keywordInput}
                placeholder='输入关键字后回车'
                className='w-64'
                onChange={(event) => setKeywordInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    updateSearch({ keyword: keywordInput.trim() })
                  }
                }}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='status'>账号状态</Label>
              <Select
                value={search.status || 'ALL'}
                onValueChange={(value) =>
                  updateSearch({ status: value === 'ALL' ? '' : value })
                }
              >
                <SelectTrigger id='status' className='w-36'>
                  <SelectValue placeholder='全部状态' />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='ALL'>全部状态</SelectItem>
                  {USER_STATUSES.map((status) => (
                    <SelectItem key={status} value={status}>
                      {USER_STATUS_LABELS[status]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='page-size'>每页条数</Label>
              <Select
                value={String(search.size)}
                onValueChange={(value) => updateSearch({ size: Number(value) })}
              >
                <SelectTrigger id='page-size' className='w-28'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PAGE_SIZES.map((size) => (
                    <SelectItem key={size} value={String(size)}>
                      {size}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <Card>
            <CardContent>
              <UsersTable
                users={usersQuery.data?.list ?? []}
                isPending={usersQuery.isPending}
                hasError={usersQuery.isError}
                isStatusUpdating={statusMutation.isPending}
                onEditRoles={setEditingUser}
                onToggleStatus={(user) => statusMutation.mutate(user)}
                onRetry={() => void usersQuery.refetch()}
              />
            </CardContent>
          </Card>

          <PaginationBar
            page={search.page}
            size={search.size}
            total={usersQuery.data?.total ?? 0}
            isDisabled={usersQuery.isPending}
            onPageChange={(page) => updateSearch({ page })}
          />

          {editingUser && (
            <UserRolesDialog
              // 换用户时重新挂载，初始勾选状态直接来自 props
              key={editingUser.publicId}
              user={editingUser}
              isPending={rolesMutation.isPending}
              onOpenChange={(open) => {
                if (!open) setEditingUser(null)
              }}
              onSubmit={(roles) => {
                rolesMutation.mutate({ publicId: editingUser.publicId, roles })
              }}
            />
          )}
        </div>
      </Main>
    </>
  )
}
