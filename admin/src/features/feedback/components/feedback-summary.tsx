import { Card, CardContent } from '@/components/ui/card'
import type { AdminFeedbackSummary } from '../types'

interface FeedbackSummaryProps {
  summary: AdminFeedbackSummary | undefined
  isPending: boolean
  hasError: boolean
}

function formatCount(value: number): string {
  return value.toLocaleString('zh-CN')
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

/**
 * 反馈统计看板。
 *
 * 数据全部来自 `/admin/feedback/summary`，没有评价时只展示空态；
 * 踩占比在无评价时显示占位符，避免出现 0% 的假信号。
 */
export function FeedbackSummary({ summary, isPending, hasError }: FeedbackSummaryProps) {
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
            反馈聚合加载失败，请稍后重试。
          </p>
        </CardContent>
      </Card>
    )
  }

  const total = summary.upCount + summary.downCount
  if (total === 0) {
    return (
      <Card>
        <CardContent>
          <p className='text-muted-foreground py-6 text-center text-sm'>
            当前筛选范围内暂无反馈数据。
          </p>
        </CardContent>
      </Card>
    )
  }

  const downRate = `${((summary.downCount / total) * 100).toFixed(1)}%`

  return (
    <div className='grid gap-4 lg:grid-cols-3'>
      <KpiCard
        title='好评'
        value={formatCount(summary.upCount)}
        detail={`共 ${formatCount(total)} 条反馈`}
      />
      <KpiCard
        title='差评'
        value={formatCount(summary.downCount)}
        detail={`差评占比 ${downRate}`}
      />
      <Card>
        <CardContent>
          <p className='text-muted-foreground text-sm'>差评原因分布</p>
          {summary.reasons.length === 0 ? (
            <p className='text-muted-foreground mt-2 text-sm'>暂无差评原因</p>
          ) : (
            <ul className='mt-2 grid gap-1 text-sm'>
              {summary.reasons.map((row) => (
                <li key={row.reasonCode} className='flex items-center justify-between gap-3'>
                  <span className='truncate'>{row.label}</span>
                  <span className='text-muted-foreground shrink-0 text-xs'>
                    {formatCount(row.total)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
