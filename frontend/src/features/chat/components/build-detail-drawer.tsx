import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  BadgeCheck,
  Box,
  ChartColumn,
  ChevronRight,
  CircuitBoard,
  Cpu,
  Fan,
  Gauge,
  Gpu,
  HardDrive,
  MemoryStick,
  Package,
  Power,
  Radar,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-react'

import type { BuildResult } from '@/features/sessions/api'
import { cn } from '@/shared/lib/utils'
import { Badge } from '@/shared/ui/badge'
import { Button } from '@/shared/ui/button'
import { Popover, PopoverContent, PopoverTitle, PopoverTrigger } from '@/shared/ui/popover'
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/shared/ui/sheet'

import {
  BuildCompatibilityList,
  COMPATIBILITY_STATUS_LABEL_KEYS,
  COMPATIBILITY_STATUS_STYLES,
  visibleCompatibilityChecks,
} from './build-compatibility-list'
import {
  BudgetAllocationChart,
  BudgetWaterWave,
  BuildGauge,
  PerformanceRadarChart,
  ScoreSemicircle,
} from './build-detail-charts'
import { BuildDetailModule } from './build-detail-module'
import { BuildHardwareTable } from './build-hardware-table'
import {
  BUDGET_LABEL_KEYS,
  BUDGET_STYLES,
  CATEGORY_LABEL_KEYS,
  formatMark,
  findBenchmark,
  GAUGE_SCALE_MAX,
  gaugeScaleFor,
  resolveBudgetSlices,
  resolveBudgetUsage,
  resolvePriceNotice,
  toGaugeValue,
  WORKLOAD_LABEL_KEYS,
} from './build-result-meta'

/** 雷达图的固定轴：性能维度评分，不使用预算占比 */
const DEMO_PERFORMANCE_AXES = [
  { key: 'CPU', labelKey: 'chat.build.detailRadarCpu', value: 88 },
  { key: 'GPU', labelKey: 'chat.build.detailRadarGpu', value: 92 },
  { key: 'MEMORY', labelKey: 'chat.build.detailRadarMemory', value: 76 },
  { key: 'STORAGE', labelKey: 'chat.build.detailRadarStorage', value: 81 },
  { key: 'COOLING', labelKey: 'chat.build.detailRadarCooling', value: 73 },
  { key: 'EXPANSION', labelKey: 'chat.build.detailRadarExpansion', value: 68 },
] as const

/**
 * 以下三项为 UI 占位演示值：当前没有功耗与综合评分的实测数据源，
 * 仅用于撑起图表版式，接入真实数据后必须整体替换。
 */
const DEMO_POWER_WATTS = 486
const DEMO_PSU_WATTS = 850
const DEMO_OVERALL_SCORE = 92

const CATEGORY_ICONS: Record<string, typeof Cpu> = {
  CPU: Cpu,
  GPU: Gpu,
  MOTHERBOARD: CircuitBoard,
  MEMORY: MemoryStick,
  STORAGE: HardDrive,
  PSU: Power,
  CASE: Box,
  COOLER: Fan,
}

export interface BuildDetailDrawerProps {
  readonly result: BuildResult
  readonly open: boolean
  readonly onOpenChange: (open: boolean) => void
  /** 正文演示价声明的兜底信号，与摘要卡使用同一判定 */
  readonly demoPriceHint?: boolean
}

/**
 * 配置详情抽屉。
 *
 * 右侧仪表盘式抽屉：预算分配与性能画像、硬件清单、兼容性校验与预算用量、
 * 推荐理由与基准数据四列并排，底部用仪表盘与半圆表汇总关键读数。
 *
 * 预算、跑分与校验结论来自结构化结果；性能画像、整机功耗与综合评分
 * 当前没有数据源，使用明确标注的演示值占位，仅保证 UI 版式完整。
 */
export function BuildDetailDrawer({
  result,
  open,
  onOpenChange,
  demoPriceHint = false,
}: BuildDetailDrawerProps) {
  const { t } = useTranslation()
  const priceNotice = resolvePriceNotice(result, demoPriceHint)
  const overall = result.overallCompatibility
  const workloadKey = result.workloadProfile
    ? WORKLOAD_LABEL_KEYS[result.workloadProfile]
    : undefined
  const workloadLabel = result.workloadProfile
    ? workloadKey
      ? t(workloadKey)
      : result.workloadProfile
    : null

  const budgetSlices = useMemo(() => resolveBudgetSlices(result), [result])
  const budgetUsage = useMemo(() => resolveBudgetUsage(result), [result])
  const checks = useMemo(
    () => visibleCompatibilityChecks(result.compatibility),
    [result.compatibility],
  )
  const passedCount = checks.filter((check) => check.status === 'PASS').length

  // 雷达轴：固定性能维度，值为 0-100 的演示评分
  const radarAxes = useMemo(
    () =>
      DEMO_PERFORMANCE_AXES.map((axis) => ({
        key: axis.key,
        label: t(axis.labelKey),
        value: axis.value,
      })),
    [t],
  )

  const reasonByHardwareId = useMemo(
    () => new Map((result.componentReasons ?? []).map((item) => [item.hardwareId, item])),
    [result.componentReasons],
  )

  const benchmarks = result.components.filter((component) => component.benchmark !== null)
  const cpuBenchmark = findBenchmark(result.components, 'CPU')
  const gpuBenchmark = findBenchmark(result.components, 'GPU')
  const storageBenchmark = findBenchmark(result.components, 'STORAGE')

  const categoryLabel = (category: string): string => {
    const key = CATEGORY_LABEL_KEYS[category]
    return key ? t(key) : category
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        showCloseButton={false}
        className="w-[96vw] gap-0 border-l border-border/70 bg-background p-0 sm:max-w-[min(1560px,96vw)] xl:w-[92vw]"
        data-testid="build-detail-dialog"
      >
        <div className="flex h-full min-h-0 flex-col">
          <SheetHeader className="flex shrink-0 flex-row flex-wrap items-center justify-between gap-3 border-b border-border/60 px-4 py-2.5">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-clay/10">
                <BadgeCheck className="size-4 text-clay" aria-hidden="true" />
              </span>
              <SheetTitle className="text-base font-semibold">
                {t('chat.build.detailTitle')}
              </SheetTitle>
              {workloadLabel ? (
                <Badge
                  variant="outline"
                  className="border-clay/30 bg-clay/10 text-[var(--cds-orange-500)] dark:text-[var(--cds-orange-250)]"
                >
                  {t('chat.build.workload.label')}：{workloadLabel}
                </Badge>
              ) : null}
              <Badge className={cn('border', COMPATIBILITY_STATUS_STYLES[overall])}>
                {t('chat.build.compatibilityShort')}：{t(COMPATIBILITY_STATUS_LABEL_KEYS[overall])}
              </Badge>
              <Badge className={cn('border', BUDGET_STYLES[result.budgetStatus])}>
                {t(BUDGET_LABEL_KEYS[result.budgetStatus])}
              </Badge>
            </div>

            <SheetClose asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                className="shrink-0"
                aria-label={t('chat.build.detailClose')}
              >
                <X className="size-4" aria-hidden="true" />
              </Button>
            </SheetClose>

            <SheetDescription className="sr-only">
              {t('chat.build.detailDescription')}
            </SheetDescription>
          </SheetHeader>

          <div className="min-h-0 flex-1 overflow-y-auto px-3.5 py-2.5 xl:flex xl:flex-col xl:overflow-hidden">
            {priceNotice === 'DEMO' ? (
              <div
                role="note"
                className="mb-2.5 flex shrink-0 items-start gap-2 rounded-xl border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning"
              >
                <ShieldAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                <div>
                  <p className="font-semibold">{t('chat.build.demoBanner')}</p>
                  <p className="mt-0.5 leading-relaxed opacity-90">
                    {t('chat.build.demoBannerDetail')}
                  </p>
                </div>
              </div>
            ) : null}

            {/* lg 双列时按内容高度排布；xl 四列必须拉伸到同一行高，否则卡片会溢出被裁 */}
            <div className="flex flex-col gap-2.5 lg:grid lg:grid-cols-2 lg:items-start xl:min-h-0 xl:flex-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.62fr)_minmax(0,1.1fr)_minmax(0,1.08fr)] xl:grid-rows-[minmax(0,1fr)] xl:items-stretch">
              {/* 第一列：预算分配 + 性能画像雷达 */}
              <div className="flex min-h-0 min-w-0 flex-col gap-3">
                <BuildDetailModule
                  title={t('chat.build.detailBudget')}
                  icon={ChartColumn}
                  className="min-h-0 flex-[4]"
                  bodyClassName="flex min-h-0 flex-col"
                  delayMs={0}
                >
                  <BudgetAllocationChart
                    items={budgetSlices.map((slice) => ({
                      key: slice.category,
                      label: categoryLabel(slice.category),
                      amountFen: slice.amountFen,
                      ratio: slice.ratio,
                    }))}
                  />
                </BuildDetailModule>
                <BuildDetailModule
                  title={t('chat.build.detailRadar')}
                  icon={Radar}
                  className="min-h-0 flex-[5]"
                  bodyClassName="flex min-h-0 flex-col items-center justify-center p-1"
                  delayMs={60}
                >
                  <PerformanceRadarChart axes={radarAxes} />
                </BuildDetailModule>
              </div>

              {/* 第二列：硬件清单（独占整列高度，表格内部滚动） */}
              <div className="flex min-h-0 min-w-0 flex-col">
                <BuildDetailModule
                  title={t('chat.build.detailHardware')}
                  icon={Package}
                  className="min-h-0 flex-1"
                  bodyClassName="pt-1"
                  delayMs={120}
                  action={
                    // 视觉占位：交互方案待定，先不绑定点击行为
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-6 gap-0.5 px-1.5 text-[11px] text-[var(--cds-orange-500)] hover:bg-clay/10 hover:text-[var(--cds-orange-500)] dark:text-[var(--cds-orange-250)]"
                    >
                      {t('chat.build.detailMore')}
                      <ChevronRight className="size-3" aria-hidden="true" />
                    </Button>
                  }
                >
                  <BuildHardwareTable components={result.components} />
                </BuildDetailModule>
              </div>

              {/* 第三列：兼容性校验 + 预算用量 */}
              <div className="flex min-h-0 min-w-0 flex-col gap-3">
                <BuildDetailModule
                  title={t('chat.build.detailChecks')}
                  icon={ShieldCheck}
                  className="min-h-0 flex-[6]"
                  bodyClassName="flex min-h-0 flex-col px-3 py-2"
                  delayMs={180}
                  action={
                    <Badge className="border border-border bg-muted px-1.5 text-[10px] text-muted-foreground">
                      {passedCount}/{checks.length}
                    </Badge>
                  }
                >
                  <BuildCompatibilityList checks={result.compatibility} heading={false} />
                </BuildDetailModule>
                <BuildDetailModule
                  title={t('chat.build.detailUsage')}
                  icon={Gauge}
                  className="min-h-[176px] shrink-0"
                  bodyClassName="flex min-h-0 flex-col justify-center py-2"
                  delayMs={240}
                >
                  {budgetUsage && result.budgetMaxFen ? (
                    <BudgetWaterWave
                      ratio={budgetUsage.ratio}
                      totalFen={result.totalPriceFen}
                      budgetFen={result.budgetMaxFen}
                      title={t('chat.build.detailBudgetHint')}
                      budgetLabel={t('chat.build.budgetMax')}
                      currentLabel={t('chat.build.detailCurrent')}
                      overLabel={t('chat.build.detailOver')}
                      remainingLabel={t('chat.build.detailRemaining')}
                    />
                  ) : (
                    <p className="text-center text-sm text-muted-foreground">
                      {t('chat.build.noBudget')}
                    </p>
                  )}
                </BuildDetailModule>
              </div>

              {/* 第四列：推荐理由（含逐件理由）+ 基准数据 */}
              <div className="flex min-h-0 min-w-0 flex-col gap-3">
                <BuildDetailModule
                  title={t('chat.build.detailReason')}
                  icon={Sparkles}
                  className="max-h-[46%] shrink-0"
                  bodyClassName="flex min-h-0 flex-col"
                  delayMs={300}
                  action={
                    result.componentReasons && result.componentReasons.length > 0 ? (
                      // 逐件理由改用浮层卡片：不占用模块高度，也不改变四列布局
                      <Popover>
                        <PopoverTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 gap-0.5 px-1.5 text-[11px] text-muted-foreground hover:text-foreground"
                          >
                            {t('chat.build.detailReasonsOpen')}
                            <ChevronRight className="size-3" aria-hidden="true" />
                          </Button>
                        </PopoverTrigger>
                        <PopoverContent
                          align="end"
                          side="bottom"
                          sideOffset={8}
                          className="max-h-[60vh] w-[440px] max-w-[calc(100vw-2rem)] overflow-y-auto p-4"
                        >
                          <PopoverTitle className="text-[13px] font-semibold text-foreground/80">
                            {t('chat.build.detailPartReasons')}
                          </PopoverTitle>
                          <ul className="mt-2 flex flex-col gap-2">
                            {result.componentReasons.map((item) => (
                              <li
                                key={`${item.hardwareCategory}-${item.hardwareId}`}
                                className="rounded-lg bg-muted/40 px-3 py-2.5"
                              >
                                <div className="flex items-center gap-2">
                                  <span className="text-[13px] font-semibold text-foreground/85">
                                    {categoryLabel(item.hardwareCategory)}
                                  </span>
                                  {item.scoreContribution !== undefined ? (
                                    <span className="ml-auto text-[12px] tabular-nums text-muted-foreground">
                                      {t('chat.build.detailContribution')}{' '}
                                      {formatMark(item.scoreContribution)}
                                    </span>
                                  ) : null}
                                </div>
                                <p className="mt-1 text-[13px] leading-relaxed break-words text-foreground/75">
                                  {item.reason}
                                </p>
                              </li>
                            ))}
                          </ul>
                        </PopoverContent>
                      </Popover>
                    ) : null
                  }
                >
                  <blockquote className="shrink-0 border-l-2 border-clay/50 pl-2.5 text-[13px] leading-relaxed text-foreground/85">
                    {result.reasonSummary || t('chat.build.noReason')}
                  </blockquote>
                </BuildDetailModule>

                <BuildDetailModule
                  title={t('chat.build.detailBenchmarks')}
                  icon={Gauge}
                  className="min-h-0 flex-1"
                  bodyClassName="flex min-h-0 flex-col"
                  delayMs={360}
                >
                  {benchmarks.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      {t('chat.build.detailNoBenchmark')}
                    </p>
                  ) : (
                    <ul className="flex h-full min-h-0 flex-col gap-1.5">
                      {benchmarks.map((component) => {
                        const benchmark = component.benchmark!
                        const scale = gaugeScaleFor(component.category)
                        const CategoryIcon = CATEGORY_ICONS[component.category] ?? Gauge
                        const reason = component.hardwareId
                          ? reasonByHardwareId.get(component.hardwareId)
                          : undefined

                        return (
                          <li
                            key={component.category}
                            className="flex min-h-0 flex-1 flex-col justify-center gap-1.5 rounded-xl bg-surface px-2.5 py-1.5"
                            title={reason?.reason}
                          >
                            <div className="flex items-center gap-1.5">
                              <CategoryIcon
                                className="size-3.5 shrink-0 text-clay"
                                aria-hidden="true"
                              />
                              <span
                                className="min-w-0 flex-1 truncate text-[12.5px] font-medium text-foreground/90"
                                title={component.modelName ?? undefined}
                              >
                                {component.modelName}
                              </span>
                              <span className="shrink-0 rounded-full bg-clay/10 px-1.5 py-0.5 text-[10px] font-semibold text-[var(--cds-orange-500)] dark:text-[var(--cds-orange-250)]">
                                {benchmark.type}
                              </span>
                            </div>
                            {/* 只有真实得分一个指标，不再编造核心数/显存等未提供字段 */}
                            <div className="flex items-center gap-2">
                              <span className="shrink-0 text-[17px] leading-none font-semibold tabular-nums text-foreground">
                                {formatMark(benchmark.score)}
                              </span>
                              {scale ? (
                                <span className="h-1 min-w-0 flex-1 overflow-hidden rounded-full bg-border/50">
                                  <span
                                    className="block h-full rounded-full"
                                    style={{
                                      width: `${toGaugeValue(benchmark.score, scale)}%`,
                                      background:
                                        'linear-gradient(90deg, var(--cds-orange-600), var(--cds-clay) 60%, var(--cds-orange-400))',
                                    }}
                                  />
                                </span>
                              ) : null}
                            </div>
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </BuildDetailModule>
              </div>
            </div>
          </div>

          <SheetFooter className="hidden h-[180px] shrink-0 flex-row items-stretch gap-3 border-t border-border/60 bg-surface-raised/70 px-4 py-2 xl:flex">
            <div className="flex w-[26%] shrink-0 items-stretch gap-2">
              <div className="min-w-0 flex-1">
                <BuildGauge
                  value={cpuBenchmark ? toGaugeValue(cpuBenchmark.score, GAUGE_SCALE_MAX.CPU) : 0}
                  displayValue={cpuBenchmark ? formatMark(cpuBenchmark.score) : '—'}
                  label={`${t('chat.build.category.cpu')} ${t('chat.build.benchmark')}`}
                  hint={t('chat.build.detailGaugeScale')}
                />
              </div>
              <div className="min-w-0 flex-1">
                <BuildGauge
                  value={gpuBenchmark ? toGaugeValue(gpuBenchmark.score, GAUGE_SCALE_MAX.GPU) : 0}
                  displayValue={gpuBenchmark ? formatMark(gpuBenchmark.score) : '—'}
                  label={`${t('chat.build.category.gpu')} ${t('chat.build.benchmark')}`}
                  hint={t('chat.build.detailGaugeScale')}
                />
              </div>
            </div>

            <div className="min-w-0 flex-1">
              <ScoreSemicircle
                value={DEMO_OVERALL_SCORE}
                displayValue={String(DEMO_OVERALL_SCORE)}
                title={t('chat.build.detailOverallScore')}
                subtitle={t('chat.build.detailOverallScoreSubtitle')}
                hint={t('chat.build.detailOverallScoreHint')}
              />
            </div>

            <div className="flex w-[26%] shrink-0 items-stretch gap-2">
              <div className="min-w-0 flex-1">
                <BuildGauge
                  value={
                    storageBenchmark
                      ? toGaugeValue(storageBenchmark.score, GAUGE_SCALE_MAX.STORAGE)
                      : 0
                  }
                  displayValue={storageBenchmark ? formatMark(storageBenchmark.score) : '—'}
                  label={`${t('chat.build.category.storage')} ${t('chat.build.benchmark')}`}
                  hint={t('chat.build.detailGaugeScale')}
                />
              </div>
              <div className="min-w-0 flex-1">
                <BuildGauge
                  value={toGaugeValue(DEMO_POWER_WATTS, DEMO_PSU_WATTS)}
                  displayValue={`${DEMO_POWER_WATTS}W`}
                  label={t('chat.build.detailPower')}
                  hint={t('chat.build.detailPowerHint', { psu: DEMO_PSU_WATTS })}
                />
              </div>
            </div>
          </SheetFooter>
        </div>
      </SheetContent>
    </Sheet>
  )
}
