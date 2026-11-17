import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { BadgeCheck, ChartColumn, ShieldAlert } from 'lucide-react'

import type { BuildResult } from '@/features/sessions/api'
import { formatFen } from '@/shared/lib/format'
import { cn } from '@/shared/lib/utils'
import { Badge } from '@/shared/ui/badge'
import { Button } from '@/shared/ui/button'

import {
  BuildCompatibilityList,
  COMPATIBILITY_STATUS_LABEL_KEYS,
  COMPATIBILITY_STATUS_STYLES,
  isBlockingPending,
} from './build-compatibility-list'
import { BuildComponentRow } from './build-result-component-row'
import { BuildDetailDrawer } from './build-detail-drawer'
import {
  BUDGET_LABEL_KEYS,
  BUDGET_STYLES,
  resolveBudgetUsage,
  resolvePriceNotice,
  WORKLOAD_LABEL_KEYS,
} from './build-result-meta'

export interface BuildResultCardProps {
  readonly result: BuildResult
  /**
   * 正文演示价声明的兜底信号。
   *
   * Stage 3 的 `build_result` 投影暂未携带 priceSource；只要正文明确写出
   * 「演示价格」，卡片也必须显著标注，宁可多标也不能把演示价当真实在售。
   */
  readonly demoPriceHint?: boolean
}

/**
 * 配置结果卡片（摘要视图）。
 *
 * 卡片只消费结构化结果，不做价格或参数的二次推断；金额统一由整数分渲染。
 * 数据完整性提示与价格免责声明常驻，避免用户把查询快照当成实时报价。
 * 完整图表、跑分与逐件理由统一收敛到右侧详情抽屉。
 */
export function BuildResultCard({ result, demoPriceHint = false }: BuildResultCardProps) {
  const { t } = useTranslation()
  const [isDetailOpen, setIsDetailOpen] = useState(false)
  const priceNotice = resolvePriceNotice(result, demoPriceHint)
  const budgetUsage = resolveBudgetUsage(result)
  const overall = result.overallCompatibility
  const workloadKey = result.workloadProfile
    ? WORKLOAD_LABEL_KEYS[result.workloadProfile]
    : undefined
  const workloadLabel = result.workloadProfile
    ? workloadKey
      ? t(workloadKey)
      : result.workloadProfile
    : null
  const blockingPendingCount = result.compatibility.filter(isBlockingPending).length
  // 理由只按 hardwareId 关联到硬件行；匹配不到或组件缺少标识时整行不展示理由
  const reasonByHardwareId = new Map(
    (result.componentReasons ?? []).map((item) => [item.hardwareId, item.reason]),
  )

  return (
    <section
      className="mt-1 overflow-hidden rounded-2xl border border-border/70 bg-surface text-card-foreground shadow-sm"
      aria-label={t('chat.build.title')}
      data-testid="build-result-card"
    >
      <header className="flex flex-wrap items-center gap-2 border-b border-border/60 px-5 py-3.5">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-clay/10">
          <BadgeCheck className="size-3.5 text-clay" aria-hidden="true" />
        </span>
        <h3 className="font-serif text-base">{t('chat.build.title')}</h3>
        <Badge className={cn('border', COMPATIBILITY_STATUS_STYLES[overall])}>
          {t('chat.build.compatibilityShort')}：{t(COMPATIBILITY_STATUS_LABEL_KEYS[overall])}
        </Badge>
        <Badge className={cn('border', BUDGET_STYLES[result.budgetStatus])}>
          {t(BUDGET_LABEL_KEYS[result.budgetStatus])}
        </Badge>
        {workloadLabel ? (
          <Badge className="border border-clay/30 bg-clay/10 text-[var(--cds-orange-500)] dark:text-[var(--cds-orange-250)]">
            {t('chat.build.workload.label')}：{workloadLabel}
          </Badge>
        ) : null}
        {result.buildId ? (
          <span className="ml-auto font-mono text-[0.6875rem] text-muted-foreground">
            {t('chat.build.buildId')} {result.buildId}
          </span>
        ) : null}
      </header>

      {/* 阻断级待核验项必须在顶部汇总，避免用户只看到卡片下方的弱化徽标 */}
      {blockingPendingCount > 0 ? (
        <div
          role="status"
          className="flex items-start gap-2 border-b border-dashed border-destructive/40 bg-destructive/5 px-5 py-2 text-sm text-destructive"
        >
          <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <p>{t('chat.build.pendingChecks', { count: blockingPendingCount })}</p>
        </div>
      ) : null}

      {/* 演示价是数据诚信红线：必须在卡片顶部显著提示，不能只在底部小字出现 */}
      {priceNotice === 'DEMO' ? (
        <div
          role="note"
          className="flex items-start gap-2 border-b border-warning/40 bg-warning/10 px-5 py-3 text-sm text-warning"
        >
          <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <div>
            <p className="font-semibold">{t('chat.build.demoBanner')}</p>
            <p className="mt-0.5 text-xs leading-relaxed">{t('chat.build.demoBannerDetail')}</p>
          </div>
        </div>
      ) : null}

      {/* 价格与预算并排：预算条只表达比例，金额仍以文本给出，颜色不单独承载结论 */}
      <div className="grid gap-4 border-b border-border/60 bg-muted/40 px-5 py-4 sm:grid-cols-[minmax(0,0.9fr)_minmax(0,1.3fr)_auto] sm:items-center">
        <div>
          <p className="text-[11px] tracking-wide text-muted-foreground">{t('chat.build.total')}</p>
          <p className="text-2xl leading-tight font-semibold tabular-nums">
            {formatFen(result.totalPriceFen)}
          </p>
        </div>

        <div className="min-w-0">
          <div className="flex items-baseline justify-between gap-3 text-[11px] text-muted-foreground">
            <span>{t('chat.build.budgetMax')}</span>
            <span className="tabular-nums">
              {result.budgetMaxFen === null
                ? t('chat.build.noBudget')
                : formatFen(result.budgetMaxFen)}
            </span>
          </div>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full transition-[width] duration-700 ease-out"
              style={{
                width: budgetUsage ? `${Math.min(100, budgetUsage.ratio)}%` : '0%',
                background:
                  result.budgetStatus === 'OVER_BUDGET'
                    ? 'linear-gradient(90deg, var(--cds-orange-400), var(--destructive))'
                    : 'linear-gradient(90deg, var(--cds-orange-400), var(--cds-clay) 55%, var(--cds-orange-250))',
              }}
            />
          </div>
          <p className="mt-1 text-[11px] tabular-nums text-muted-foreground">
            {budgetUsage
              ? `${t('chat.build.detailBudgetHint')} ${budgetUsage.ratio.toFixed(1)}%`
              : t('chat.build.noBudget')}
          </p>
        </div>

        <Button
          variant="outline"
          size="sm"
          className="justify-self-start gap-1.5 border-clay/35 bg-clay/10 text-[var(--cds-orange-500)] hover:bg-clay/15 hover:text-[var(--cds-orange-600)] sm:justify-self-end dark:text-[var(--cds-orange-250)] dark:hover:text-[var(--cds-orange-150)]"
          onClick={() => setIsDetailOpen(true)}
        >
          <ChartColumn className="size-3.5" aria-hidden="true" />
          {t('chat.build.detailOpen')}
        </Button>
      </div>

      <p className="border-b border-border/60 bg-muted/40 px-5 py-2 text-xs leading-relaxed text-muted-foreground">
        {t('chat.build.integrity')}
      </p>

      <div className="border-b border-border/60">
        <h4 className="px-5 pt-3 text-[11px] font-medium tracking-wide text-muted-foreground">
          {t('chat.build.detailHardware')}
        </h4>
        <ul className="divide-y divide-border/50">
          {result.components.map((component) => (
            <BuildComponentRow
              key={component.category}
              component={component}
              reason={
                component.hardwareId ? reasonByHardwareId.get(component.hardwareId) : undefined
              }
            />
          ))}
        </ul>
      </div>

      <div className="border-b border-border/60 px-5 py-3.5">
        <h4 className="text-[11px] font-medium tracking-wide text-muted-foreground">
          {t('chat.build.reason')}
        </h4>
        <blockquote className="mt-1.5 border-l-2 border-clay/45 pl-3 text-sm leading-relaxed">
          {result.reasonSummary || t('chat.build.noReason')}
        </blockquote>
      </div>

      <div className="px-5 py-3.5">
        <BuildCompatibilityList checks={result.compatibility} />
      </div>

      {/* 价格免责声明常驻展示，不随是否有演示价而变化 */}
      <p className="border-t border-border/60 bg-muted/40 px-5 py-2 text-xs leading-relaxed text-muted-foreground">
        {t('chat.build.disclaimer')}
      </p>

      <BuildDetailDrawer
        result={result}
        open={isDetailOpen}
        onOpenChange={setIsDetailOpen}
        demoPriceHint={demoPriceHint}
      />
    </section>
  )
}
