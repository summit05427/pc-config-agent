import { useTranslation } from 'react-i18next'
import { ExternalLink, ShieldAlert } from 'lucide-react'

import type {
    BuildBudgetStatus,
    BuildCompatibilityStatus,
    BuildComponent,
    BuildResult,
} from '@/features/sessions/api'
import { formatFen } from '@/shared/lib/format'
import { cn } from '@/shared/lib/utils'
import { Badge } from '@/shared/ui/badge'

/** 后端类别固定为这八类；未知类别原样展示，不隐藏数据 */
const CATEGORY_LABEL_KEYS: Record<string, string> = {
    CPU: 'chat.build.category.cpu',
    MOTHERBOARD: 'chat.build.category.motherboard',
    MEMORY: 'chat.build.category.memory',
    GPU: 'chat.build.category.gpu',
    PSU: 'chat.build.category.psu',
    CASE: 'chat.build.category.case',
    COOLER: 'chat.build.category.cooler',
    STORAGE: 'chat.build.category.storage',
}

const STATUS_STYLES: Record<BuildCompatibilityStatus, string> = {
    PASS: 'border-success/30 bg-success/10 text-success',
    WARNING: 'border-warning/40 bg-warning/10 text-warning',
    FAIL: 'border-destructive/40 bg-destructive/10 text-destructive',
    // UNKNOWN 必须与 PASS 视觉区分：虚线 + 弱化配色，绝不使用成功色
    UNKNOWN: 'border-dashed border-border-strong bg-muted text-muted-foreground',
}

const STATUS_LABEL_KEYS: Record<BuildCompatibilityStatus, string> = {
    PASS: 'chat.build.status.pass',
    WARNING: 'chat.build.status.warning',
    FAIL: 'chat.build.status.fail',
    UNKNOWN: 'chat.build.status.unknown',
}

const BUDGET_LABEL_KEYS: Record<BuildBudgetStatus, string> = {
    WITHIN_BUDGET: 'chat.build.budget.within',
    OVER_BUDGET: 'chat.build.budget.over',
    NO_BUDGET: 'chat.build.budget.noBudget',
    UNKNOWN: 'chat.build.budget.unknown',
}

const BUDGET_STYLES: Record<BuildBudgetStatus, string> = {
    WITHIN_BUDGET: 'border-success/30 bg-success/10 text-success',
    OVER_BUDGET: 'border-destructive/40 bg-destructive/10 text-destructive',
    NO_BUDGET: 'border-border bg-muted text-muted-foreground',
    UNKNOWN: 'border-dashed border-border-strong bg-muted text-muted-foreground',
}

const isMockPrice = (component: BuildComponent): boolean => component.priceSource === 'MOCK_DEMO'

/** 无核验时间或明确 verifiedPrice=false 都按未核验展示，不冒充已核验 */
const isUnverified = (component: BuildComponent): boolean =>
    component.verifiedPrice === false ||
    (component.verifiedPrice === null && component.offerVerifiedAt === null)

const hasDemoPrice = (result: BuildResult, hint: boolean): boolean =>
    hint ||
    (result.demoOfferCount ?? 0) > 0 ||
    result.offerDataStatus === 'MIXED_DEMO' ||
    result.components.some(isMockPrice)

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
 * 配置结果卡片。
 *
 * 卡片只消费结构化结果，不做价格或参数的二次推断；金额统一由整数分渲染。
 * 数据完整性提示与价格免责声明常驻，避免用户把查询快照当成实时报价。
 */
export function BuildResultCard({ result, demoPriceHint = false }: BuildResultCardProps) {
    const { t } = useTranslation()
    const showDemo = hasDemoPrice(result, demoPriceHint)
    const overall = result.overallCompatibility

    return (
        <section
            className="mt-1 overflow-hidden rounded-xl border border-border bg-card text-card-foreground"
            aria-label={t('chat.build.title')}
            data-testid="build-result-card"
        >
            <header className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
                <h3 className="font-serif text-base">{t('chat.build.title')}</h3>
                <Badge className={cn('border', STATUS_STYLES[overall])}>
                    {t('chat.build.compatibilityShort')}：{t(STATUS_LABEL_KEYS[overall])}
                </Badge>
                <Badge className={cn('border', BUDGET_STYLES[result.budgetStatus])}>
                    {t(BUDGET_LABEL_KEYS[result.budgetStatus])}
                </Badge>
                {result.buildId ? (
                    <span className="ml-auto font-mono text-[0.6875rem] text-muted-foreground">
                        {t('chat.build.buildId')} {result.buildId}
                    </span>
                ) : null}
            </header>

            {/* 演示价是数据诚信红线：必须在卡片顶部显著提示，不能只在底部小字出现 */}
            {showDemo ? (
                <div
                    role="note"
                    className="flex items-start gap-2 border-b border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning"
                >
                    <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                    <div>
                        <p className="font-semibold">{t('chat.build.demoBanner')}</p>
                        <p className="mt-0.5 text-xs leading-relaxed">
                            {t('chat.build.demoBannerDetail')}
                        </p>
                    </div>
                </div>
            ) : null}

            <p className="border-b border-border bg-muted/40 px-4 py-2 text-xs leading-relaxed text-muted-foreground">
                {t('chat.build.integrity')}
            </p>

            <ul className="divide-y divide-border">
                {result.components.map((component) => (
                    <BuildComponentRow key={component.category} component={component} />
                ))}
            </ul>

            <div className="border-t border-border px-4 py-4">
                <dl className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
                    <div>
                        <dt className="text-xs text-muted-foreground">{t('chat.build.total')}</dt>
                        <dd className="text-xl font-semibold tabular-nums">
                            {formatFen(result.totalPriceFen)}
                        </dd>
                    </div>
                    <div>
                        <dt className="text-xs text-muted-foreground">{t('chat.build.budgetMax')}</dt>
                        <dd className="text-sm tabular-nums">
                            {result.budgetMaxFen === null
                                ? t('chat.build.noBudget')
                                : formatFen(result.budgetMaxFen)}
                        </dd>
                    </div>
                </dl>
            </div>

            <div className="border-t border-border px-4 py-3">
                <h4 className="text-xs font-medium text-muted-foreground">
                    {t('chat.build.reason')}
                </h4>
                <p className="mt-1 text-sm leading-relaxed">
                    {result.reasonSummary || t('chat.build.noReason')}
                </p>
            </div>

            <div className="border-t border-border px-4 py-3">
                <h4 className="text-xs font-medium text-muted-foreground">
                    {t('chat.build.compatibility')}
                </h4>
                {result.compatibility.length === 0 ? (
                    <p className="mt-1 text-sm text-muted-foreground">
                        {t('chat.build.noChecks')}
                    </p>
                ) : (
                    <ul className="mt-2 space-y-2">
                        {result.compatibility.map((check, index) => (
                            <li
                                key={`${check.rule}-${index}`}
                                className="flex flex-wrap items-start gap-2 text-sm"
                            >
                                <Badge className={cn('border', STATUS_STYLES[check.status])}>
                                    {t(STATUS_LABEL_KEYS[check.status])}
                                </Badge>
                                <span className="font-medium">{check.rule}</span>
                                {check.message ? (
                                    <span className="text-muted-foreground">{check.message}</span>
                                ) : null}
                            </li>
                        ))}
                    </ul>
                )}
            </div>

            {/* 价格免责声明常驻展示，不随是否有演示价而变化 */}
            <p className="border-t border-border bg-muted/40 px-4 py-2 text-xs leading-relaxed text-muted-foreground">
                {t('chat.build.disclaimer')}
            </p>
        </section>
    )
}

interface BuildComponentRowProps {
    readonly component: BuildComponent
}

/** 单类硬件行：左侧参数与来源，右侧报价与购买链接 */
function BuildComponentRow({ component }: BuildComponentRowProps) {
    const { t } = useTranslation()
    const categoryKey = CATEGORY_LABEL_KEYS[component.category]
    const categoryLabel = categoryKey ? t(categoryKey) : component.category
    const hasModel = Boolean(component.modelName)
    const mock = isMockPrice(component)
    const unverified = isUnverified(component)

    return (
        <li className="px-4 py-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs text-muted-foreground">{categoryLabel}</span>
                        {mock ? (
                            <Badge className="border border-warning/40 bg-warning/10 text-warning">
                                {t('chat.build.demoTag')}
                            </Badge>
                        ) : hasModel && unverified ? (
                            <Badge className="border border-border bg-muted text-muted-foreground">
                                {t('chat.build.unverifiedTag')}
                            </Badge>
                        ) : null}
                    </div>

                    <p className="mt-1 font-medium break-words">
                        {hasModel ? component.modelName : t('chat.build.emptyModel')}
                    </p>
                    {component.brand ? (
                        <p className="text-xs text-muted-foreground">
                            {t('chat.build.brand')}：{component.brand}
                        </p>
                    ) : null}
                    {component.title ? (
                        <p className="text-xs break-words text-muted-foreground">
                            {t('chat.build.product')}：{component.title}
                        </p>
                    ) : null}
                    {component.specSummary ? (
                        <p className="mt-1 text-xs leading-relaxed break-words text-muted-foreground">
                            {component.specSummary}
                        </p>
                    ) : null}

                    <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                        {component.platform ? (
                            <span>
                                {t('chat.build.platform')}：{component.platform}
                            </span>
                        ) : null}
                        {component.seller ? (
                            <span>
                                {t('chat.build.seller')}：{component.seller}
                            </span>
                        ) : null}
                        {component.benchmark ? (
                            <span>
                                {t('chat.build.benchmark')}：{component.benchmark.type}{' '}
                                {component.benchmark.score}
                            </span>
                        ) : null}
                        {component.offerVerifiedAt ? (
                            <span>
                                {t('chat.build.verifiedAt')}：{component.offerVerifiedAt}
                            </span>
                        ) : null}
                    </div>
                </div>

                {hasModel ? (
                    <div className="flex shrink-0 flex-col items-end gap-1">
                        <span className="text-sm font-semibold tabular-nums">
                            {formatFen(component.priceFen)}
                        </span>
                        {component.purchaseUrl ? (
                            <a
                                href={component.purchaseUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 text-xs text-primary underline-offset-4 hover:underline"
                            >
                                {t('chat.build.buy')}
                                <ExternalLink className="size-3" aria-hidden="true" />
                            </a>
                        ) : (
                            <span className="text-xs text-muted-foreground">
                                {t('chat.build.noLink')}
                            </span>
                        )}
                    </div>
                ) : null}
            </div>
        </li>
    )
}
