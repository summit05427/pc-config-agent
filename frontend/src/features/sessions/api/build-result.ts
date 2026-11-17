import type {
  BuildBenchmark,
  BuildBudgetStatus,
  BuildCompatibilityCheck,
  BuildCompatibilityRiskLevel,
  BuildCompatibilityStatus,
  BuildComponent,
  BuildComponentReason,
  BuildResult,
  BuildWorkloadProfile,
} from './types'

type UnknownRecord = Record<string, unknown>

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

/**
 * 同时兼容 Agent 的 snake_case 投影与 Java DTO 的 camelCase 字段。
 *
 * `done.build_result` 由 Agent 投影为 snake_case；若后续改为直传 Java DTO，
 * 解析边界无需再改，展示层只认归一化后的 camelCase。
 */
const read = (record: UnknownRecord, ...keys: string[]): unknown => {
  for (const key of keys) {
    if (key in record) {
      return record[key]
    }
  }
  return undefined
}

const toText = (value: unknown): string => (typeof value === 'string' ? value : '')

const toTextOrNull = (value: unknown): string | null => {
  const text = toText(value).trim()
  return text ? text : null
}

/** 金额只接受整数分；浮点数视为脏数据，避免静默产生小数误差 */
const toInteger = (value: unknown): number | null =>
  typeof value === 'number' && Number.isInteger(value) ? value : null

const toBooleanOrNull = (value: unknown): boolean | null =>
  typeof value === 'boolean' ? value : null

const COMPATIBILITY_STATUSES: readonly BuildCompatibilityStatus[] = [
  'PASS',
  'WARNING',
  'FAIL',
  'UNKNOWN',
]

/** 无法识别的状态一律降级为 UNKNOWN，绝不默认成 PASS */
const toCompatibilityStatus = (value: unknown): BuildCompatibilityStatus => {
  const text = toText(value).toUpperCase()
  return COMPATIBILITY_STATUSES.find((status) => status === text) ?? 'UNKNOWN'
}

const BUDGET_STATUSES: readonly BuildBudgetStatus[] = [
  'WITHIN_BUDGET',
  'OVER_BUDGET',
  'NO_BUDGET',
]

/** 新老版本共存的用途取值；不在列表内的值一律忽略，避免展示错误标签 */
const WORKLOAD_PROFILES: readonly BuildWorkloadProfile[] = [
  'GENERAL',
  'GAMING',
  'MEDIA',
  'VIDEO_EDITING',
  'PROGRAMMING',
  'RENDERING',
  'AI_INFERENCE',
  'CREATIVE',
  'WORKSTATION',
  'OFFICE',
  'BALANCED',
]

const RISK_LEVELS: readonly BuildCompatibilityRiskLevel[] = ['BLOCKING', 'ADVISORY']

/**
 * 三个新增字段均可选：历史消息不含它们，缺失或取值非法时只丢弃该字段，
 * 不能因此让整份 `build_result` 被判为畸形。
 */
const toWorkloadProfile = (value: unknown): BuildWorkloadProfile | undefined => {
  const text = toText(value).toUpperCase()
  return WORKLOAD_PROFILES.find((profile) => profile === text)
}

const toRiskLevel = (value: unknown): BuildCompatibilityRiskLevel | undefined => {
  const text = toText(value).toUpperCase()
  return RISK_LEVELS.find((level) => level === text)
}

const toBudgetStatus = (value: unknown): BuildBudgetStatus => {
  const text = toText(value).toUpperCase()
  return BUDGET_STATUSES.find((status) => status === text) ?? 'UNKNOWN'
}

const isHttpUrl = (value: string): boolean => /^https?:\/\//i.test(value)

/** 只接受绝对 http(s) 地址；图片与购买链接共用同一道守卫 */
const toHttpUrl = (value: unknown): string | null => {
  const url = toTextOrNull(value)
  return url && isHttpUrl(url) ? url : null
}

/** 跑分既支持嵌套 `benchmark`，也支持 Java DTO 的扁平字段 */
const toBenchmark = (record: UnknownRecord): BuildBenchmark | null => {
  const nested = read(record, 'benchmark')
  if (isRecord(nested)) {
    const type = toText(read(nested, 'type', 'benchmark_type', 'benchmarkType'))
    const score = read(nested, 'score', 'benchmark_score', 'benchmarkScore')
    if (type && typeof score === 'number' && Number.isFinite(score)) {
      return { type, score }
    }
  }

  const type = toText(read(record, 'benchmark_type', 'benchmarkType'))
  const score = read(record, 'benchmark_score', 'benchmarkScore')
  return type && typeof score === 'number' && Number.isFinite(score) ? { type, score } : null
}

const toComponent = (value: unknown): BuildComponent | null => {
  if (!isRecord(value)) {
    return null
  }

  // 类别是唯一必填项：Agent 会为缺失类别补空位，前端据此渲染占位行
  const category = toText(read(value, 'category')).trim()
  if (!category) {
    return null
  }

  return {
    category,
    hardwareId: toTextOrNull(read(value, 'hardware_id', 'hardwareId')),
    modelName: toText(read(value, 'model_name', 'modelName')),
    specSummary: toText(read(value, 'spec_summary', 'specSummary')),
    priceFen: toInteger(read(value, 'price_fen', 'priceFen')) ?? 0,
    purchaseUrl: toHttpUrl(read(value, 'purchase_url', 'purchaseUrl')),
    imageUrl: toHttpUrl(read(value, 'image_url', 'imageUrl')),
    benchmark: toBenchmark(value),
    offerVerifiedAt: toTextOrNull(read(value, 'offer_verified_at', 'verifiedAt')),
    brand: toTextOrNull(read(value, 'brand')),
    title: toTextOrNull(read(value, 'title', 'product_title', 'productTitle')),
    platform: toTextOrNull(read(value, 'platform')),
    seller: toTextOrNull(read(value, 'seller')),
    priceSource: toTextOrNull(read(value, 'price_source', 'priceSource')),
    priceType: toTextOrNull(read(value, 'price_type', 'priceType')),
    verifiedPrice: toBooleanOrNull(read(value, 'verified_price', 'verifiedPrice')),
  }
}

/**
 * 逐件选型理由：`hardwareId` 与 `reason` 是展示与匹配的最小必要字段，
 * 任一缺失或类型不符就跳过该项，不能因此让整份结果被判为畸形。
 * 得分与价格只做透传，缺失时省略，绝不补默认值。
 */
const toComponentReason = (value: unknown): BuildComponentReason | null => {
  if (!isRecord(value)) {
    return null
  }

  const hardwareId = toTextOrNull(read(value, 'hardware_id', 'hardwareId'))
  const reason = toTextOrNull(read(value, 'reason'))
  if (!hardwareId || !reason) {
    return null
  }

  const scoreContribution = toInteger(read(value, 'score_contribution', 'scoreContribution'))
  const priceFen = toInteger(read(value, 'price_fen', 'priceFen'))

  return {
    hardwareCategory: toText(read(value, 'hardware_category', 'hardwareCategory')),
    hardwareId,
    reason,
    ...(scoreContribution !== null ? { scoreContribution } : {}),
    ...(priceFen !== null ? { priceFen } : {}),
  }
}

const toCheck = (value: unknown): BuildCompatibilityCheck | null => {
  if (!isRecord(value)) {
    return null
  }

  const rule = toText(read(value, 'rule', 'ruleName', 'rule_name', 'ruleId', 'rule_id'))
  if (!rule) {
    return null
  }

  const ruleId = toText(read(value, 'rule_id', 'ruleId'))
  const riskLevel = toRiskLevel(read(value, 'risk_level', 'riskLevel'))

  return {
    rule,
    status: toCompatibilityStatus(read(value, 'status')),
    message: toText(read(value, 'message')),
    ...(ruleId ? { ruleId } : {}),
    ...(riskLevel ? { riskLevel } : {}),
  }
}

/** 兼容投影后的 `compatibility[]` 与 Java 的 `compatibilityReport.checks[]` */
const readChecks = (record: UnknownRecord): unknown[] => {
  const direct = read(record, 'compatibility')
  if (Array.isArray(direct)) {
    return direct
  }

  const report = read(record, 'compatibility_report', 'compatibilityReport')
  if (isRecord(report)) {
    const checks = read(report, 'checks')
    return Array.isArray(checks) ? checks : []
  }

  return []
}

const WORST_ORDER: readonly BuildCompatibilityStatus[] = ['FAIL', 'UNKNOWN', 'WARNING', 'PASS']

/**
 * 合并多个结论时取最严重者，优先级 FAIL > UNKNOWN > WARNING > PASS。
 *
 * 没有任何检查项时返回 UNKNOWN，而不是 PASS：缺少证据不能视为通过。
 */
const resolveOverallStatus = (
  provided: unknown,
  checks: readonly BuildCompatibilityCheck[],
): BuildCompatibilityStatus => {
  const explicit = toText(provided).toUpperCase()
  const matched = COMPATIBILITY_STATUSES.find((status) => status === explicit)
  if (matched) {
    return matched
  }
  if (checks.length === 0) {
    return 'UNKNOWN'
  }
  return checks.reduce<BuildCompatibilityStatus>((worst, check) => {
    return WORST_ORDER.indexOf(check.status) < WORST_ORDER.indexOf(worst) ? check.status : worst
  }, 'PASS')
}

/**
 * 解析 `done.build_result`。
 *
 * 顶层结构异常返回 null，让消息回退到 Markdown；单个硬件条目损坏只跳过该条，
 * 不牵连整张卡片。金额全程按整数分处理，缺失总价时用整数分累加兜底。
 */
export function parseBuildResult(value: unknown): BuildResult | null {
  if (!isRecord(value)) {
    return null
  }

  const rawComponents = read(value, 'components')
  if (!Array.isArray(rawComponents)) {
    return null
  }

  const components = rawComponents
    .map(toComponent)
    .filter((component): component is BuildComponent => component !== null)
  if (components.length === 0) {
    return null
  }

  const compatibility = readChecks(value)
    .map(toCheck)
    .filter((check): check is BuildCompatibilityCheck => check !== null)

  const report = read(value, 'compatibility_report', 'compatibilityReport')
  const providedOverall = isRecord(report)
    ? read(report, 'overall_status', 'overallStatus')
    : read(value, 'overall_status', 'overallStatus')

  const totalFromWire = toInteger(read(value, 'total_price_fen', 'totalPriceFen'))
  const totalPriceFen =
    totalFromWire ?? components.reduce((sum, component) => sum + component.priceFen, 0)

  const workloadProfile = toWorkloadProfile(read(value, 'workload_profile', 'workloadProfile'))
  const scoringVersion = toTextOrNull(read(value, 'scoring_version', 'scoringVersion'))

  // 逐件理由整体缺失时保持 undefined，历史消息的渲染结果与新增前完全一致
  const rawReasons = read(value, 'component_reasons', 'componentReasons')
  const componentReasons = Array.isArray(rawReasons)
    ? rawReasons
        .map(toComponentReason)
        .filter((reason): reason is BuildComponentReason => reason !== null)
    : []

  return {
    buildId: toTextOrNull(read(value, 'build_id', 'buildId')),
    components,
    totalPriceFen,
    budgetMaxFen: toInteger(read(value, 'budget_max_fen', 'budgetMaxFen')),
    budgetStatus: toBudgetStatus(read(value, 'budget_status', 'budgetStatus')),
    overallCompatibility: resolveOverallStatus(providedOverall, compatibility),
    compatibility,
    reasonSummary: toText(read(value, 'reason_summary', 'reasonSummary')),
    offerDataStatus: toTextOrNull(read(value, 'offer_data_status', 'offerDataStatus')),
    verifiedOfferCount: toInteger(read(value, 'verified_offer_count', 'verifiedOfferCount')),
    demoOfferCount: toInteger(read(value, 'demo_offer_count', 'demoOfferCount')),
    ...(workloadProfile ? { workloadProfile } : {}),
    ...(scoringVersion ? { scoringVersion } : {}),
    ...(componentReasons.length > 0 ? { componentReasons } : {}),
  }
}
