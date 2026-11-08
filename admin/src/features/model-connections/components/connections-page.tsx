import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearch } from '@tanstack/react-router'
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
import { adminProvidersQueryOptions } from '@/features/models/api/admin-models-api'
import { adminConnectionsQueryOptions } from '../api/admin-model-connections-api'
import {
  CONNECTION_STATUSES,
  CONNECTION_STATUS_LABELS,
  type ConnectionStatus,
} from '../types'
import { ConnectionsTable } from './connections-table'

const PAGE_SIZES = [10, 20, 50, 100]

/**
 * 模型连接只读页。
 *
 * 管理端只观察用户 BYOK 连接状态，不提供任何修改入口；
 * 表格只展示凭证掩码与状态，密文与明文密钥不会出现在页面。
 */
export function ConnectionsPage() {
  const search = useSearch({ from: '/_authenticated/model-connections/' })
  // 绑定 from 后 search 更新函数才会收窄到本路由的 schema，而不是全路由并集
  const navigate = useNavigate({ from: '/model-connections/' })
  const [userIdInput, setUserIdInput] = useState(search.userId)
  const providersQuery = useQuery(adminProvidersQueryOptions())
  const connectionsQuery = useQuery(
    adminConnectionsQueryOptions({
      page: search.page,
      size: search.size,
      userId: search.userId || undefined,
      provider: search.provider || undefined,
      status: search.status || undefined,
    })
  )

  function updateSearch(next: {
    userId?: string
    provider?: string
    status?: ConnectionStatus | ''
  }) {
    navigate({
      to: '/model-connections',
      search: (previous) => ({
        userId: next.userId ?? previous.userId ?? '',
        provider: next.provider ?? previous.provider ?? '',
        status: next.status ?? previous.status ?? '',
        size: previous.size ?? 20,
        page: 1,
      }),
    })
  }

  function changePage(page: number) {
    navigate({
      to: '/model-connections',
      search: (previous) => ({ ...previous, page }),
    })
  }

  function changeSize(size: number) {
    navigate({
      to: '/model-connections',
      search: (previous) => ({ ...previous, size, page: 1 }),
    })
  }

  return (
    <>
      <Header fixed />
      <Main className='flex flex-1 flex-col gap-4 sm:gap-6'>
        <div className='flex flex-col gap-4'>
          <div>
            <h1 className='text-2xl font-bold tracking-tight'>模型连接</h1>
            <p className='text-sm text-muted-foreground'>
              只读查看用户 BYOK 连接与凭证状态；页面只展示掩码，不展示密钥内容。
            </p>
          </div>

          <div className='flex flex-wrap items-end gap-3'>
            <div className='grid gap-1.5'>
              <Label htmlFor='connection-user-id'>用户 ID</Label>
              <Input
                id='connection-user-id'
                value={userIdInput}
                placeholder='用户公开 ID，回车查询'
                className='w-64'
                maxLength={36}
                onChange={(event) => setUserIdInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    updateSearch({ userId: userIdInput.trim() })
                  }
                }}
                onBlur={() => updateSearch({ userId: userIdInput.trim() })}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='connection-provider'>Provider</Label>
              <Select
                value={search.provider || 'ALL'}
                onValueChange={(value) =>
                  updateSearch({ provider: value === 'ALL' ? '' : value })
                }
              >
                <SelectTrigger id='connection-provider' className='w-40'>
                  <SelectValue placeholder='全部 Provider' />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='ALL'>全部 Provider</SelectItem>
                  {(providersQuery.data ?? []).map((item) => (
                    <SelectItem key={item.code} value={item.code}>
                      {item.displayName}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='connection-status'>连接状态</Label>
              <Select
                value={search.status || 'ALL'}
                onValueChange={(value) =>
                  updateSearch({
                    status: value === 'ALL' ? '' : (value as ConnectionStatus),
                  })
                }
              >
                <SelectTrigger id='connection-status' className='w-32'>
                  <SelectValue placeholder='全部状态' />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='ALL'>全部状态</SelectItem>
                  {CONNECTION_STATUSES.map((item) => (
                    <SelectItem key={item} value={item}>
                      {CONNECTION_STATUS_LABELS[item]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='connection-page-size'>每页条数</Label>
              <Select
                value={String(search.size)}
                onValueChange={(value) => changeSize(Number(value))}
              >
                <SelectTrigger id='connection-page-size' className='w-28'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PAGE_SIZES.map((item) => (
                    <SelectItem key={item} value={String(item)}>
                      {item}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <Card>
            <CardContent>
              <ConnectionsTable
                connections={connectionsQuery.data?.list ?? []}
                isPending={connectionsQuery.isPending}
                hasError={connectionsQuery.isError}
                onRetry={() => void connectionsQuery.refetch()}
              />
            </CardContent>
          </Card>

          <PaginationBar
            page={search.page}
            size={search.size}
            total={connectionsQuery.data?.total ?? 0}
            isDisabled={connectionsQuery.isPending}
            onPageChange={changePage}
          />
        </div>
      </Main>
    </>
  )
}
