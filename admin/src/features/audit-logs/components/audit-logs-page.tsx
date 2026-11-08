import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { formatDateTime } from '@/lib/format'
import { Badge } from '@/components/ui/badge'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { PaginationBar } from '@/components/pagination-bar'
import { TableState } from '@/components/table-state'
import { auditLogsQueryOptions } from '@/features/audit-logs/api/audit-logs-api'
import { AUDIT_EVENTS, getAuditEventLabel } from '@/features/audit-logs/types'

const PAGE_SIZES = [10, 20, 50, 100]

export function AuditLogsPage() {
  const search = useSearch({ from: '/_authenticated/audit-logs/' })
  const navigate = useNavigate()
  const [usernameInput, setUsernameInput] = useState(search.username)

  const auditLogsQuery = useQuery(
    auditLogsQueryOptions({
      page: search.page,
      size: search.size,
      event: search.event || undefined,
      username: search.username || undefined,
    })
  )

  function updateSearch(next: {
    page?: number
    event?: string
    username?: string
  }) {
    navigate({
      to: '/audit-logs',
      search: (previous) => ({
        event: next.event ?? previous.event ?? '',
        username: next.username ?? previous.username ?? '',
        size: previous.size ?? 20,
        page: next.page ?? 1,
      }),
    })
  }

  function changeSize(size: number) {
    navigate({
      to: '/audit-logs',
      search: (previous) => ({
        event: previous.event ?? '',
        username: previous.username ?? '',
        size,
        // 切换每页条数后回到第一页，避免页码越界
        page: 1,
      }),
    })
  }

  return (
    <>
      <Header fixed />
      <Main className='flex flex-1 flex-col gap-4 sm:gap-6'>
        <div className='flex flex-col gap-4'>
          <div>
            <h1 className='text-2xl font-bold tracking-tight'>审计日志</h1>
            <p className='text-sm text-muted-foreground'>
              记录认证相关事件；用户名精确匹配，时间按倒序展示。
            </p>
          </div>

          <div className='flex flex-wrap items-end gap-3'>
            <div className='grid gap-1.5'>
              <Label htmlFor='event'>事件类型</Label>
              <Select
                value={search.event || 'ALL'}
                onValueChange={(value) =>
                  updateSearch({ event: value === 'ALL' ? '' : value })
                }
              >
                <SelectTrigger id='event' className='w-48'>
                  <SelectValue placeholder='全部事件' />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='ALL'>全部事件</SelectItem>
                  {AUDIT_EVENTS.map((event) => (
                    <SelectItem key={event} value={event}>
                      {getAuditEventLabel(event)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='username'>用户名</Label>
              <Input
                id='username'
                value={usernameInput}
                placeholder='精确用户名，回车查询'
                className='w-56'
                onChange={(event) => setUsernameInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    updateSearch({ username: usernameInput.trim() })
                  }
                }}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='audit-page-size'>每页条数</Label>
              <Select
                value={String(search.size)}
                onValueChange={(value) => changeSize(Number(value))}
              >
                <SelectTrigger id='audit-page-size' className='w-28'>
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
              {auditLogsQuery.isPending ? (
                <TableState kind='loading' description='正在获取审计日志…' />
              ) : auditLogsQuery.isError ? (
                <TableState
                  kind='error'
                  title='审计日志加载失败'
                  description='请稍后重试，或点击下方按钮重新加载。'
                  onRetry={() => void auditLogsQuery.refetch()}
                />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>发生时间</TableHead>
                      <TableHead>事件</TableHead>
                      <TableHead>用户名</TableHead>
                      <TableHead>来源 IP</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {auditLogsQuery.data.list.map((log, index) => (
                      // 审计表没有对外主键，用「时间 + 用户名 + 事件 + 序号」保证 key 稳定
                      <TableRow
                        key={`${log.createdAt}-${log.username}-${log.event}-${index}`}
                      >
                        <TableCell>{formatDateTime(log.createdAt)}</TableCell>
                        <TableCell>
                          <Badge variant='outline'>
                            {getAuditEventLabel(log.event)}
                          </Badge>
                        </TableCell>
                        <TableCell>{log.username}</TableCell>
                        <TableCell>{log.ip ?? '—'}</TableCell>
                      </TableRow>
                    ))}
                    {auditLogsQuery.data.list.length === 0 && (
                      <TableState
                        kind='empty'
                        colSpan={4}
                        title='没有符合条件的审计记录'
                        description='调整事件类型或用户名后再试。'
                      />
                    )}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          <PaginationBar
            page={search.page}
            size={search.size}
            total={auditLogsQuery.data?.total ?? 0}
            isDisabled={auditLogsQuery.isPending}
            onPageChange={(page) => updateSearch({ page })}
          />
        </div>
      </Main>
    </>
  )
}
