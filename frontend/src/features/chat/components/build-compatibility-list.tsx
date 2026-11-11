import { useTranslation } from 'react-i18next'

import type {
    BuildCompatibilityCheck,
    BuildCompatibilityStatus,
} from '@/features/sessions/api'
import { cn } from '@/shared/lib/utils'
import { Badge } from '@/shared/ui/badge'

/** 状态配色唯一事实来源：UNKNOWN 必须与 PASS 视觉区分，绝不使用成功色 */
export const COMPATIBILITY_STATUS_STYLES: Record<BuildCompatibilityStatus, string> = {
    PASS: 'border-success/30 bg-success/10 text-success',
    WARNING: 'border-warning/40 bg-warning/10 text-warning',
    FAIL: 'border-destructive/40 bg-destructive/10 text-destructive',
    UNKNOWN: 'border-dashed border-border-strong bg-muted text-muted-foreground',
}

export const COMPATIBILITY_STATUS_LABEL_KEYS: Record<BuildCompatibilityStatus, string> = {
    PASS: 'chat.build.status.pass',
    WARNING: 'chat.build.status.warning',
    FAIL: 'chat.build.status.fail',
    UNKNOWN: 'chat.build.status.unknown',
}

/** 只有 UNKNOWN + BLOCKING 才算「待核验」；其余组合不得升级为阻断提示 */
export const isBlockingPending = (check: BuildCompatibilityCheck): boolean =>
    check.status === 'UNKNOWN' && check.riskLevel === 'BLOCKING'

/**
 * 机箱限高：产品策略已改为数据缺失时默认通过，前端不再展示该条结论。
 * 同时用 ruleId 与规则名兜底，历史消息可能只带其中一个。
 */
const HIDDEN_RULE_IDS = new Set(['cooler_case_height'])
const HIDDEN_RULE_NAME = '散热器高度'

const isHiddenCheck = (check: BuildCompatibilityCheck): boolean =>
    (check.ruleId !== undefined && HIDDEN_RULE_IDS.has(check.ruleId)) ||
    check.rule.includes(HIDDEN_RULE_NAME)

export interface BuildCompatibilityListProps {
    readonly checks: readonly BuildCompatibilityCheck[]
}

/**
 * 兼容性校验清单。
 *
 * 卡片与详情面板共用同一份实现，避免两处对 PASS / UNKNOWN 的口径出现漂移。
 */
export function BuildCompatibilityList({ checks }: BuildCompatibilityListProps) {
    const { t } = useTranslation()
    const visibleChecks = checks.filter((check) => !isHiddenCheck(check))

    return (
        <div>
            <h4 className="text-xs font-medium text-muted-foreground">
                {t('chat.build.compatibility')}
            </h4>
            {visibleChecks.length === 0 ? (
                <p className="mt-1 text-sm text-muted-foreground">{t('chat.build.noChecks')}</p>
            ) : (
                <ul className="mt-2 space-y-2">
                    {visibleChecks.map((check, index) => (
                        <li
                            key={`${check.rule}-${index}`}
                            className="flex flex-wrap items-start gap-2 text-sm"
                        >
                            <Badge
                                className={cn('border', COMPATIBILITY_STATUS_STYLES[check.status])}
                            >
                                {t(COMPATIBILITY_STATUS_LABEL_KEYS[check.status])}
                            </Badge>
                            {/* 待核验用虚线 + 危险色独立标注，绝不能复用 PASS 的成功色 */}
                            {isBlockingPending(check) ? (
                                <Badge className="border border-dashed border-destructive/50 bg-background text-destructive">
                                    {t('chat.build.status.pendingVerification')}
                                </Badge>
                            ) : check.riskLevel === 'ADVISORY' ? (
                                <Badge className="border border-border bg-muted text-muted-foreground">
                                    {t('chat.build.risk.advisory')}
                                </Badge>
                            ) : null}
                            <span className="font-medium">{check.rule}</span>
                            {check.message ? (
                                <span className="text-muted-foreground">{check.message}</span>
                            ) : null}
                        </li>
                    ))}
                </ul>
            )}
        </div>
    )
}
