import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'

import { modelUsageQueryOptions } from '@/features/usage/api'

/** 汇总接口未返回时统一显示占位符，避免用 0 冒充真实统计 */
const UNKNOWN_VALUE = '—'

/**
 * 使用统计概览：只展示累计 Token 数。
 *
 * 数据来自 `GET /api/v1/users/me/model-usage` 的 `totalTokens`，
 * 与明细面板共用同一个 Query，切换分区不会重复请求。
 */
export function UsageOverview() {
  const { t, i18n } = useTranslation()
  const usageQuery = useQuery(modelUsageQueryOptions({ page: 1, size: 1 }))

  const totalTokens = usageQuery.data?.totalTokens ?? 0
  const value = usageQuery.isSuccess
    ? new Intl.NumberFormat(i18n.language).format(totalTokens)
    : UNKNOWN_VALUE

  return (
    <section className="rounded-[var(--cds-panel-radius)] border border-border bg-surface px-4 py-5 sm:px-5">
      <p className="text-xs text-muted-foreground">{t('settings.usage.metrics.totalTokens')}</p>
      <p className="tabular mt-2 text-3xl font-semibold tracking-[-0.02em] text-foreground">
        {value}
      </p>
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
        {usageQuery.isError
          ? t('settings.usage.totalTokensError')
          : t('settings.usage.totalTokensHint')}
      </p>
    </section>
  )
}
