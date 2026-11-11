import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ExternalLink } from 'lucide-react'

import type { BuildComponent } from '@/features/sessions/api'
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

export const isMockPrice = (component: BuildComponent): boolean =>
    component.priceSource === 'MOCK_DEMO'

/** 无核验时间或明确 verifiedPrice=false 都按未核验展示，不冒充已核验 */
const isUnverified = (component: BuildComponent): boolean =>
    component.verifiedPrice === false ||
    (component.verifiedPrice === null && component.offerVerifiedAt === null)

/** 超过该长度的理由默认折叠，避免长文本把卡片撑开 */
const REASON_COLLAPSE_THRESHOLD = 80

export interface BuildComponentRowProps {
    readonly component: BuildComponent
    /** 该硬件的确定性选型理由；按 hardwareId 匹配不到时不传，行内不出现任何占位 */
    readonly reason?: string
}

/** 单类硬件行：左侧参数、选型理由与来源，右侧报价与购买链接 */
export function BuildComponentRow({ component, reason }: BuildComponentRowProps) {
    const { t } = useTranslation()
    const [isReasonExpanded, setIsReasonExpanded] = useState(false)
    const categoryKey = CATEGORY_LABEL_KEYS[component.category]
    const categoryLabel = categoryKey ? t(categoryKey) : component.category
    const hasModel = Boolean(component.modelName)
    const mock = isMockPrice(component)
    const unverified = isUnverified(component)
    const isLongReason = Boolean(reason && reason.length > REASON_COLLAPSE_THRESHOLD)

    return (
        <li className="px-4 py-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
                {/* 图片仅作辅助识别，alt 留空避免和型号文本重复朗读 */}
                {component.imageUrl ? (
                    <img
                        src={component.imageUrl}
                        alt=""
                        loading="lazy"
                        className="mt-0.5 size-14 shrink-0 rounded-md border border-border bg-muted object-cover"
                    />
                ) : null}
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

                    {/* 理由文本由服务端确定性生成，这里只原样展示，不改写也不补充结论 */}
                    {reason ? (
                        <div className="mt-2 rounded-md bg-muted/50 px-2 py-1.5">
                            <p className="text-xs font-medium text-muted-foreground">
                                {t('chat.build.componentReason')}
                            </p>
                            <p
                                className={cn(
                                    'mt-0.5 text-xs leading-relaxed break-words text-muted-foreground',
                                    isLongReason && !isReasonExpanded ? 'line-clamp-2' : null,
                                )}
                            >
                                {reason}
                            </p>
                            {isLongReason ? (
                                <button
                                    type="button"
                                    className="mt-1 text-xs text-primary underline-offset-4 hover:underline"
                                    aria-expanded={isReasonExpanded}
                                    onClick={() => setIsReasonExpanded((expanded) => !expanded)}
                                >
                                    {isReasonExpanded
                                        ? t('chat.build.reasonCollapse')
                                        : t('chat.build.reasonExpand')}
                                </button>
                            ) : null}
                        </div>
                    ) : null}
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
