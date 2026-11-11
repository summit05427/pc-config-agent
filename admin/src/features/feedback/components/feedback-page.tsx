import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { toast } from 'sonner'
import { Card, CardContent } from '@/components/ui/card'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { PaginationBar } from '@/components/pagination-bar'
import {
  adminFeedbackListQueryOptions,
  adminFeedbackSummaryQueryOptions,
  exportFeedbackCsv,
} from '../api/admin-feedback-api'
import { FeedbackFilters, type FeedbackFilterPatch } from './feedback-filters'
import { FeedbackSummary } from './feedback-summary'
import { FeedbackTable } from './feedback-table'

/**
 * 用户反馈页。
 *
 * 列表与统计各发一次请求，共用同一套筛选条件；导出复用当前筛选，
 * 但只导出服务端上限内的行数（10000），超出部分由服务端截断。
 */
export function FeedbackPage() {
  const search = useSearch({ from: '/_authenticated/feedback/' })
  const navigate = useNavigate({ from: '/feedback/' })
  const [isExporting, setIsExporting] = useState(false)

  const params = {
    page: search.page,
    size: search.size,
    rating: search.rating,
    reasonCode: search.reasonCode,
    userId: search.userId,
    threadId: search.threadId,
    from: search.from,
    to: search.to,
  }

  const listQuery = useQuery(adminFeedbackListQueryOptions(params))
  const summaryQuery = useQuery(adminFeedbackSummaryQueryOptions(params))

  function updateSearch(patch: FeedbackFilterPatch) {
    navigate({
      to: '/feedback',
      search: (previous) => ({
        userId: previous.userId ?? '',
        rating: patch.rating ?? previous.rating ?? '',
        reasonCode: patch.reasonCode ?? previous.reasonCode ?? '',
        threadId: patch.threadId ?? previous.threadId ?? '',
        from: patch.from ?? previous.from ?? '',
        to: patch.to ?? previous.to ?? '',
        size: previous.size ?? 20,
        // 过滤条件变化时回到第一页，避免停留在越界页码
        page: 1,
      }),
    })
  }

  function changePage(page: number) {
    navigate({ to: '/feedback', search: (previous) => ({ ...previous, page }) })
  }

  async function handleExport() {
    setIsExporting(true)
    try {
      await exportFeedbackCsv(params)
    } catch {
      // 导出走独立请求，失败不能影响列表，提示后停留在当前页
      toast.error('导出失败，请稍后重试。')
    } finally {
      setIsExporting(false)
    }
  }

  return (
    <>
      <Header fixed />
      <Main className='flex flex-1 flex-col gap-4 sm:gap-6'>
        <div className='flex flex-col gap-4'>
          <div>
            <h1 className='text-2xl font-bold tracking-tight'>用户反馈</h1>
            <p className='text-sm text-muted-foreground'>
              查看用户对助手回答的赞踩与原因，支持按会话、评分与时间筛选后导出 CSV。
            </p>
            <p className='mt-1 text-xs text-muted-foreground'>
              反馈只记录评分与备注，不包含对话正文；正文请结合会话 ID 在会话记录中排查。
            </p>
          </div>

          <FeedbackSummary
            summary={summaryQuery.data}
            isPending={summaryQuery.isPending}
            hasError={summaryQuery.isError}
          />

          <FeedbackFilters
            rating={search.rating}
            reasonCode={search.reasonCode}
            threadId={search.threadId}
            from={search.from}
            to={search.to}
            isExporting={isExporting}
            onChange={updateSearch}
            onExport={() => void handleExport()}
          />

          <Card>
            <CardContent>
              <FeedbackTable
                items={listQuery.data?.list ?? []}
                isPending={listQuery.isPending}
                hasError={listQuery.isError}
                onRetry={() => void listQuery.refetch()}
              />
            </CardContent>
          </Card>

          <PaginationBar
            page={search.page}
            size={search.size}
            total={listQuery.data?.total ?? 0}
            isDisabled={listQuery.isPending}
            onPageChange={changePage}
          />
        </div>
      </Main>
    </>
  )
}
