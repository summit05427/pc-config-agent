import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldAlert } from 'lucide-react'

import type { BuildBudgetStatus, BuildResult } from '@/features/sessions/api'
import { formatFen } from '@/shared/lib/format'
import { cn } from '@/shared/lib/utils'
import { Badge } from '@/shared/ui/badge'
import { Button } from '@/shared/ui/button'

import { BuildComponentRow, isMockPrice } from './build-result-component-row'
import {
    BuildCompatibilityList,
    COMPATIBILITY_STATUS_LABEL_KEYS,
    COMPATIBILITY_STATUS_STYLES,
    isBlockingPending,
} from './build-compatibility-list'
import { BuildDetailDialog } from './build-detail-dialog'

/** 用途画像转中文；未知取值原样展示，不做猜测 */
const WORKLOAD_LABEL_KEYS: Record<string, string> = {
    GENERAL: 'chat.build.workload.general',
    GAMING: 'chat.build.workload.gaming',
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
    const [isDetailOpen, setIsDetailOpen] = useState(false)
    const showDemo = hasDemoPrice(result, demoPriceHint)
    const overall = result.overallCompatibility
    const workloadKey = result.workloadProfile
        ? WORKLOAD_LABEL_KEYS[result.workloadProfile]
        : undefined
    const workloadLabel = result.workloadProfile
        ? (workloadKey ? t(workloadKey) : result.workloadProfile)
        : null
    const blockingPendingCount = result.compatibility.filter(isBlockingPending).length
    // 理由只按 hardwareId 关联到硬件行；匹配不到或组件缺少标识时整行不展示理由
    const reasonByHardwareId = new Map(
        (result.componentReasons ?? []).map((item) => [item.hardwareId, item.reason]),
    )

    return (
        <section
            className="mt-1 overflow-hidden rounded-xl border border-border bg-card text-card-foreground"
            aria-label={t('chat.build.title')}
            data-testid="build-result-card"
        >
            <header className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
                <h3 className="font-serif text-base">{t('chat.build.title')}</h3>
                <Badge className={cn('border', COMPATIBILITY_STATUS_STYLES[overall])}>
                    {t('chat.build.compatibilityShort')}：
                    {t(COMPATIBILITY_STATUS_LABEL_KEYS[overall])}
                </Badge>
                <Badge className={cn('border', BUDGET_STYLES[result.budgetStatus])}>
                    {t(BUDGET_LABEL_KEYS[result.budgetStatus])}
                </Badge>
                {workloadLabel ? (
                    <Badge className="border border-border bg-muted text-muted-foreground">
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
                    className="flex items-start gap-2 border-b border-dashed border-destructive/40 bg-destructive/5 px-4 py-2 text-sm text-destructive"
                >
                    <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                    <p>{t('chat.build.pendingChecks', { count: blockingPendingCount })}</p>
                </div>
            ) : null}

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
                    <BuildComponentRow
                        key={component.category}
                        component={component}
                        reason={
                            component.hardwareId
                                ? reasonByHardwareId.get(component.hardwareId)
                                : undefined
                        }
                    />
                ))}
            </ul>

            <div className="border-t border-border px-4 py-4">
                <div className="flex flex-wrap items-end justify-between gap-3">
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
                    <Button variant="outline" size="sm" onClick={() => setIsDetailOpen(true)}>
                        {t('chat.build.detailOpen')}
                    </Button>
                </div>
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
                <BuildCompatibilityList checks={result.compatibility} />
            </div>

            {/* 价格免责声明常驻展示，不随是否有演示价而变化 */}
            <p className="border-t border-border bg-muted/40 px-4 py-2 text-xs leading-relaxed text-muted-foreground">
                {t('chat.build.disclaimer')}
            </p>

            <BuildDetailDialog
                result={result}
                open={isDetailOpen}
                onOpenChange={setIsDetailOpen}
            />
        </section>
    )
}
