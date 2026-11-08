import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { normalizeError } from '@/core/http'
import { modelUsageQueryOptions, type ModelUsageItem } from '@/features/usage/api'
import { formatDateTime } from '@/shared/lib/format'
import { Button } from '@/shared/ui/button'
import { Skeleton } from '@/shared/ui/skeleton'

const PAGE_SIZE = 10
const SKELETON_ROWS = ['skeleton-a', 'skeleton-b', 'skeleton-c'] as const
const HTTP_NOT_FOUND = 404

const formatCount = (value: number | null): string => (value === null ? '—' : String(value))

/** 模型用量：当日额度、调用明细与分页；404 表示运行时未启用，整块隐藏 */
export function ModelUsagePanel() {
  const { t } = useTranslation()
  const [page, setPage] = useState(1)

  const usageQuery = useQuery({
    ...modelUsageQueryOptions({ page, size: PAGE_SIZE }),
    placeholderData: keepPreviousData,
  })

  const usage = usageQuery.data
  const totalPages = Math.max(1, Math.ceil((usage?.total ?? 0) / PAGE_SIZE))
  const currentPage = usage?.page ?? page
  const isFetching = usageQuery.isFetching

  const sourceLabel = (item: ModelUsageItem): string =>
    item.credentialSource === 'BYOK'
      ? t('settings.model.usage.sourceByok')
      : t('settings.model.usage.sourceManaged')

  if (usageQuery.isError && normalizeError(usageQuery.error).status === HTTP_NOT_FOUND) {
    return null
  }

  const quota = usage?.quota

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="text-sm font-medium text-foreground">{t('settings.model.usage.title')}</h3>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          {t('settings.model.usage.hint')}
        </p>
      </div>

      {quota ? (
        <div className="rounded-[var(--cds-panel-radius)] border border-border bg-surface px-4 py-4">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-xs text-muted-foreground">
              {t('settings.model.usage.quotaLabel')}
            </span>
            <span className="tabular text-sm font-medium text-foreground">
              {t('settings.model.usage.quotaValue', { used: quota.used, limit: quota.limit })}
            </span>
          </div>
          <progress
            className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-surface-raised accent-clay"
            value={quota.used}
            max={Math.max(1, quota.limit)}
            aria-label={t('settings.model.usage.quotaLabel')}
          />
          <p className="mt-2 text-xs text-muted-foreground">
            {t('settings.model.usage.resetAt')}: {formatDateTime(quota.resetAt)}
          </p>
        </div>
      ) : null}

      {usageQuery.isError ? (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-3 rounded-[var(--cds-panel-radius)] border border-dashed border-border px-4 py-4"
        >
          <p className="min-w-0 flex-1 text-xs leading-relaxed text-muted-foreground">
            {t('settings.model.usage.loadFailed')}
          </p>
          <Button variant="outline" size="sm" onClick={() => void usageQuery.refetch()}>
            {t('common.retry')}
          </Button>
        </div>
      ) : null}

      {usageQuery.isLoading ? (
        <div className="flex flex-col gap-2" aria-hidden="true">
          {SKELETON_ROWS.map((key) => (
            <Skeleton key={key} className="h-6 w-full" />
          ))}
        </div>
      ) : null}

      {usage && usage.list.length === 0 ? (
        <p className="rounded-[var(--cds-panel-radius)] border border-dashed border-border px-4 py-8 text-center text-xs text-muted-foreground">
          {t('settings.model.usage.empty')}
        </p>
      ) : null}

      {usage && usage.list.length > 0 ? (
        <div className="overflow-x-auto rounded-[var(--cds-panel-radius)] border border-border">
          <table className="w-full min-w-[480px] border-collapse text-xs">
            <thead className="bg-surface-raised text-muted-foreground">
              <tr>
                <th className="px-3 py-2.5 text-left font-medium">
                  {t('settings.model.usage.occurredAt')}
                </th>
                <th className="px-3 py-2.5 text-left font-medium">
                  {t('settings.model.usage.model')}
                </th>
                <th className="px-3 py-2.5 text-left font-medium">
                  {t('settings.model.usage.source')}
                </th>
                <th className="px-3 py-2.5 text-right font-medium">
                  {t('settings.model.usage.tokens')}
                </th>
              </tr>
            </thead>
            <tbody>
              {usage.list.map((item) => (
                <tr
                  key={item.invocationId}
                  className="border-t border-border transition-colors hover:bg-muted"
                >
                  <td className="whitespace-nowrap px-3 py-2.5 text-muted-foreground">
                    {formatDateTime(item.occurredAt)}
                  </td>
                  <td className="max-w-[180px] truncate px-3 py-2.5 font-mono text-foreground">
                    {item.modelKey}
                  </td>
                  <td className="px-3 py-2.5 text-muted-foreground">{sourceLabel(item)}</td>
                  <td className="tabular px-3 py-2.5 text-right text-muted-foreground">
                    {formatCount(item.promptTokens)} / {formatCount(item.completionTokens)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {usage ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            {t('settings.model.usage.pageIndicator', {
              page: currentPage,
              total: totalPages,
              count: usage.total,
            })}
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={currentPage <= 1 || isFetching}
              onClick={() => setPage(currentPage - 1)}
            >
              {t('settings.model.usage.previousPage')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={currentPage >= totalPages || isFetching}
              onClick={() => setPage(currentPage + 1)}
            >
              {t('settings.model.usage.nextPage')}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
