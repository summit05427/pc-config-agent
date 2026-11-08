import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { Card, CardContent } from '@/components/ui/card'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { PaginationBar } from '@/components/pagination-bar'
import { adminProvidersQueryOptions } from '@/features/models/api/admin-models-api'
import {
  adminUsageListQueryOptions,
  adminUsageSummaryQueryOptions,
} from '../api/admin-usage-api'
import { UsageFilters, type UsageFilterPatch } from './usage-filters'
import { UsageSummary } from './usage-summary'
import { UsageTable } from './usage-table'

/**
 * 用量与成本页。
 *
 * 汇总与明细各发一次请求：汇总只接受 Provider、模型、凭证来源与日期，
 * 明细额外支持用户、成本状态与调用结果。两者共用同一套日期口径，
 * 页面上明确提示汇总不受明细的三个过滤条件影响，避免误读。
 */
export function UsagePage() {
  const search = useSearch({ from: '/_authenticated/usage/' })
  // 绑定 from 后 search 更新函数才会收窄到本路由的 schema，而不是全路由并集
  const navigate = useNavigate({ from: '/usage/' })
  const providersQuery = useQuery(adminProvidersQueryOptions())

  const summaryQuery = useQuery(
    adminUsageSummaryQueryOptions({
      provider: search.provider || undefined,
      modelKey: search.modelKey || undefined,
      credentialSource: search.credentialSource || undefined,
      from: search.from || undefined,
      to: search.to || undefined,
    })
  )

  const usageQuery = useQuery(
    adminUsageListQueryOptions({
      page: search.page,
      size: search.size,
      userId: search.userId || undefined,
      provider: search.provider || undefined,
      modelKey: search.modelKey || undefined,
      credentialSource: search.credentialSource || undefined,
      costStatus: search.costStatus || undefined,
      status: search.status || undefined,
      from: search.from || undefined,
      to: search.to || undefined,
      order: search.order || undefined,
    })
  )

  function updateSearch(patch: UsageFilterPatch) {
    navigate({
      to: '/usage',
      search: (previous) => ({
        userId: patch.userId ?? previous.userId ?? '',
        provider: patch.provider ?? previous.provider ?? '',
        modelKey: patch.modelKey ?? previous.modelKey ?? '',
        credentialSource:
          patch.credentialSource ?? previous.credentialSource ?? '',
        costStatus: patch.costStatus ?? previous.costStatus ?? '',
        status: patch.status ?? previous.status ?? '',
        from: patch.from ?? previous.from ?? '',
        to: patch.to ?? previous.to ?? '',
        order: patch.order ?? previous.order ?? 'desc',
        size: previous.size ?? 20,
        // 过滤条件变化时回到第一页，避免停留在越界页码
        page: 1,
      }),
    })
  }

  function changePage(page: number) {
    navigate({
      to: '/usage',
      search: (previous) => ({ ...previous, page }),
    })
  }

  function changeSize(size: number) {
    navigate({
      to: '/usage',
      search: (previous) => ({ ...previous, size, page: 1 }),
    })
  }

  return (
    <>
      <Header fixed />
      <Main className='flex flex-1 flex-col gap-4 sm:gap-6'>
        <div className='flex flex-col gap-4'>
          <div>
            <h1 className='text-2xl font-bold tracking-tight'>用量与成本</h1>
            <p className='text-sm text-muted-foreground'>
              跨用户查看模型调用明细与成本分布；分页、过滤、排序与聚合全部由服务端执行。
            </p>
            <p className='mt-1 text-xs text-muted-foreground'>
              汇总按
              Provider、模型、凭证来源与日期聚合，不受用户、成本状态与调用结果筛选影响。
            </p>
          </div>

          <UsageSummary
            summary={summaryQuery.data}
            isPending={summaryQuery.isPending}
            hasError={summaryQuery.isError}
          />

          <UsageFilters
            userId={search.userId}
            provider={search.provider}
            modelKey={search.modelKey}
            credentialSource={search.credentialSource}
            costStatus={search.costStatus}
            status={search.status}
            from={search.from}
            to={search.to}
            order={search.order}
            size={search.size}
            providers={providersQuery.data ?? []}
            onChange={updateSearch}
            onSizeChange={changeSize}
          />

          <Card>
            <CardContent>
              <UsageTable
                items={usageQuery.data?.list ?? []}
                isPending={usageQuery.isPending}
                hasError={usageQuery.isError}
                onRetry={() => void usageQuery.refetch()}
              />
            </CardContent>
          </Card>

          <PaginationBar
            page={search.page}
            size={search.size}
            total={usageQuery.data?.total ?? 0}
            isDisabled={usageQuery.isPending}
            onPageChange={changePage}
          />
        </div>
      </Main>
    </>
  )
}
