import type {
  BuildBenchmark,
  BuildBudgetStatus,
  BuildComponent,
  BuildResult,
} from '@/features/sessions/api'

/** MOCK_DEMO 报价只能按演示价展示，任何位置都不得当作已核验价格 */
export const isMockPrice = (component: BuildComponent): boolean =>
  component.priceSource === 'MOCK_DEMO'

/** 硬件类别 → i18n key；未知类别原样展示，不隐藏数据 */
export const CATEGORY_LABEL_KEYS: Record<string, string> = {
  CPU: 'chat.build.category.cpu',
  MOTHERBOARD: 'chat.build.category.motherboard',
  MEMORY: 'chat.build.category.memory',
  GPU: 'chat.build.category.gpu',
  PSU: 'chat.build.category.psu',
  CASE: 'chat.build.category.case',
  COOLER: 'chat.build.category.cooler',
  STORAGE: 'chat.build.category.storage',
}

/** 用途画像 → i18n key；未知取值原样展示，不做猜测 */
export const WORKLOAD_LABEL_KEYS: Record<string, string> = {
  GENERAL: 'chat.build.workload.general',
  GAMING: 'chat.build.workload.gaming',
  MEDIA: 'chat.build.workload.media',
  VIDEO_EDITING: 'chat.build.workload.videoEditing',
  PROGRAMMING: 'chat.build.workload.programming',
  RENDERING: 'chat.build.workload.rendering',
  AI_INFERENCE: 'chat.build.workload.aiInference',
  // 以下为旧版本取值，服务端可能仍在返回
  CREATIVE: 'chat.build.workload.creative',
  WORKSTATION: 'chat.build.workload.workstation',
  OFFICE: 'chat.build.workload.office',
  BALANCED: 'chat.build.workload.balanced',
}

export const BUDGET_LABEL_KEYS: Record<BuildBudgetStatus, string> = {
  WITHIN_BUDGET: 'chat.build.budget.within',
  OVER_BUDGET: 'chat.build.budget.over',
  NO_BUDGET: 'chat.build.budget.noBudget',
  UNKNOWN: 'chat.build.budget.unknown',
}

export const BUDGET_STYLES: Record<BuildBudgetStatus, string> = {
  WITHIN_BUDGET: 'border-success/30 bg-success/10 text-success',
  OVER_BUDGET: 'border-destructive/40 bg-destructive/10 text-destructive',
  NO_BUDGET: 'border-border bg-muted text-muted-foreground',
  UNKNOWN: 'border-dashed border-border-strong bg-muted text-muted-foreground',
}

/** 价格来源提示等级：演示价、平台参考价、无需提示 */
export type BuildPriceNotice = 'DEMO' | 'OBSERVED' | 'NONE'

/**
 * 解析价格来源提示等级。
 *
 * 逐件 `priceSource` 是权威信号；聚合计数 `demoOfferCount` 统计的是
 * 「非 OWNER_VERIFIED」，平台观测价也会被计入，只在逐件来源缺失时兜底，
 * 否则会把真实在售的参考价误报成演示价。
 */
export function resolvePriceNotice(result: BuildResult, hint: boolean): BuildPriceNotice {
  const hasComponentSource = result.components.some((component) => Boolean(component.priceSource))
  const hasDemo =
    hint ||
    result.offerDataStatus === 'MIXED_DEMO' ||
    result.components.some(isMockPrice) ||
    (!hasComponentSource && (result.demoOfferCount ?? 0) > 0)
  if (hasDemo) {
    return 'DEMO'
  }
  const hasObserved =
    result.offerDataStatus === 'PLATFORM_OBSERVED_ONLY' ||
    result.components.some((component) => component.priceSource === 'PLATFORM_OBSERVED')
  return hasObserved ? 'OBSERVED' : 'NONE'
}

/** 预算用量：预算缺失或非正数时返回 null，避免展示误导性的百分比 */
export interface BuildBudgetUsage {
  /** 总价占预算比例（未钳制，超预算时会大于 100） */
  readonly ratio: number
  /** 超出的金额（分）；未超出为 0 */
  readonly overFen: number
}

export function resolveBudgetUsage(result: BuildResult): BuildBudgetUsage | null {
  const budget = result.budgetMaxFen
  if (budget === null || budget <= 0) {
    return null
  }
  return {
    ratio: (result.totalPriceFen / budget) * 100,
    overFen: Math.max(0, result.totalPriceFen - budget),
  }
}

/**
 * 仪表盘归一化参考上限（只影响弧线比例，中心始终展示真实跑分）。
 * 取值参考公开跑分榜单的一线型号量级，随数据更新可调整，不作为业务断言。
 */
export type GaugeCategory = 'CPU' | 'GPU' | 'STORAGE'

export const GAUGE_SCALE_MAX: Record<GaugeCategory, number> = {
  CPU: 180_000,
  GPU: 45_000,
  STORAGE: 75_000,
}

/** 未知类别没有可信参考上限时返回 null，不编造比例 */
export function gaugeScaleFor(category: string): number | null {
  return category in GAUGE_SCALE_MAX ? GAUGE_SCALE_MAX[category as GaugeCategory] : null
}

export function toGaugeValue(raw: number, max: number): number {
  if (!Number.isFinite(raw) || max <= 0) {
    return 0
  }
  return Math.min(100, Math.max(0, Math.round((raw / max) * 100)))
}

/** 按类别取该件硬件的跑分；缺失时返回 null，不补零冒充 */
export function findBenchmark(
  components: readonly BuildComponent[],
  category: string,
): BuildBenchmark | null {
  return components.find((component) => component.category === category)?.benchmark ?? null
}

/** 跑分千分位：与金额格式化分开，跑分是整数分值 */
export function formatMark(value: number): string {
  return Math.round(value).toLocaleString('en-US')
}

/** 各品类金额降序：预算分配图的唯一数据源 */
export interface BuildBudgetSlice {
  readonly category: string
  readonly amountFen: number
  readonly ratio: number
}

export function resolveBudgetSlices(result: BuildResult): BuildBudgetSlice[] {
  const total = result.components.reduce((sum, component) => sum + component.priceFen, 0)
  if (total <= 0) {
    return []
  }
  return [...result.components]
    .sort((left, right) => right.priceFen - left.priceFen)
    .map((component) => ({
      category: component.category,
      amountFen: component.priceFen,
      ratio: (component.priceFen / total) * 100,
    }))
}
