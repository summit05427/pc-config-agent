import {
  getCostStatusLabel,
  type AdminUsageSummary,
} from '../types'
import { Card, CardContent } from '@/components/ui/card'

interface UsageSummaryProps {
  summary: AdminUsageSummary | undefined
  isPending: boolean
  hasError: boolean
}

function formatAmount(value: number): string {
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 6 })
}

function formatCount(value: number): string {
  return value.toLocaleString('zh-CN')
}

/** 金额为空时区分「没有估算」与「多币种不可求和」，不展示 0 冒充真实费用。 */
function amountLabel(
  cost: number | null,
  currency: string | null,
  hasEstimated: boolean
): string {
  if (cost !== null) {
    return `${currency ?? ''} ${formatAmount(cost)}`.trim()
  }
  return hasEstimated ? '多币种' : '暂无定价'
}

function KpiCard({
  title,
  value,
  detail,
}: {
  title: string
  value: string
  detail: string
}) {
  return (
    <Card>
      <CardContent>
        <p className='text-muted-foreground text-sm'>{title}</p>
        <p className='mt-1 text-2xl font-semibold tracking-tight'>{value}</p>
        <p className='text-muted-foreground mt-1 text-xs'>{detail}</p>
      </CardContent>
    </Card>
  )
}

function BreakdownList({
  title,
  rows,
}: {
  title: string
  rows: { key: string; label: string; requestCount: number; totalTokens: number }[]
}) {
  return (
    <Card>
      <CardContent>
        <p className='font-medium'>{title}</p>
        {rows.length === 0 ? (
          <p className='text-muted-foreground mt-2 text-sm'>暂无数据</p>
        ) : (
          <ul className='mt-2 grid gap-1 text-sm'>
            {rows.slice(0, 5).map((row) => (
              <li key={row.key} className='flex items-center justify-between gap-3'>
                <span className='truncate'>{row.label}</span>
                <span className='text-muted-foreground shrink-0 text-xs'>
                  {formatCount(row.requestCount)} 次 / {formatCount(row.totalTokens)} token
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

/**
 * 用量聚合看板。
 *
 * 全部指标来自 `/admin/model-usage/summary`；没有数据时只展示空态，
 * 不生成趋势图、不填充示例数字。成本状态分布同时暴露未知费用与 BYOK 不计费，
 * 避免把「没有定价」误读成「费用为 0」。
 */
export function UsageSummary({ summary, isPending, hasError }: UsageSummaryProps) {
  if (isPending) {
    return (
      <Card>
        <CardContent>
          <p className='text-muted-foreground py-6 text-center text-sm'>加载中…</p>
        </CardContent>
      </Card>
    )
  }

  if (hasError || !summary) {
    return (
      <Card>
        <CardContent>
          <p className='text-destructive py-6 text-center text-sm'>
            用量聚合加载失败，请稍后重试。
          </p>
        </CardContent>
      </Card>
    )
  }

  if (summary.totals.requestCount === 0) {
    return (
      <Card>
        <CardContent>
          <p className='text-muted-foreground py-6 text-center text-sm'>
            当前筛选范围内暂无用量数据，未生成任何统计。
          </p>
        </CardContent>
      </Card>
    )
  }

  const totals = summary.totals
  return (
    <div className='flex flex-col gap-4'>
      <div className='grid gap-4 sm:grid-cols-2 xl:grid-cols-4'>
        <KpiCard
          title='调用总数'
          value={formatCount(totals.requestCount)}
          detail={`成功 ${formatCount(totals.successCount)} / 失败 ${formatCount(totals.failureCount)}`}
        />
        <KpiCard
          title='Token 总量'
          value={formatCount(totals.totalTokens)}
          detail={`输入 ${formatCount(totals.promptTokens)} / 输出 ${formatCount(totals.completionTokens)}`}
        />
        <KpiCard
          title='估算费用'
          value={amountLabel(totals.estimatedCost, totals.currency, totals.estimatedCount > 0)}
          detail={`已估算 ${formatCount(totals.estimatedCount)} 次；未知 ${formatCount(totals.unknownCostCount)} 次`}
        />
        <KpiCard
          title='BYOK 不计费'
          value={formatCount(totals.byokNotBilledCount)}
          detail='用户自带凭证，平台不承担费用'
        />
      </div>

      <div className='grid gap-4 lg:grid-cols-2'>
        <BreakdownList
          title='Provider 分布'
          rows={summary.byProvider.map((row) => ({
            key: row.provider,
            label: row.provider,
            requestCount: row.requestCount,
            totalTokens: row.totalTokens,
          }))}
        />
        <BreakdownList
          title='模型分布'
          rows={summary.byModel.map((row) => ({
            key: `${row.provider}:${row.modelKey}`,
            label: `${row.provider}:${row.modelKey}`,
            requestCount: row.requestCount,
            totalTokens: row.totalTokens,
          }))}
        />
      </div>

      <div className='flex flex-wrap gap-2 text-sm'>
        {summary.byCostStatus.map((row) => (
          <span
            key={row.costStatus}
            className='bg-muted rounded-md px-2 py-1'
          >
            {getCostStatusLabel(row.costStatus)}：{formatCount(row.requestCount)} 次
          </span>
        ))}
      </div>
    </div>
  )
}
