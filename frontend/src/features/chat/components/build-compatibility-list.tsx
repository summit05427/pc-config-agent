import { useTranslation } from 'react-i18next'
import { CircleAlert, CircleCheck, CircleDashed, CircleX } from 'lucide-react'

import type { BuildCompatibilityCheck, BuildCompatibilityStatus } from '@/features/sessions/api'
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

/** 可见校验项：摘要卡、抽屉与通过率统计共用同一份过滤口径 */
export function visibleCompatibilityChecks(
  checks: readonly BuildCompatibilityCheck[],
): BuildCompatibilityCheck[] {
  return checks.filter((check) => !isHiddenCheck(check))
}

/** 结论图标：状态不只靠颜色表达，图标与徽标同时给出语义 */
const STATUS_ICONS: Record<
  BuildCompatibilityStatus,
  { icon: typeof CircleCheck; className: string }
> = {
  PASS: { icon: CircleCheck, className: 'text-success' },
  WARNING: { icon: CircleAlert, className: 'text-warning' },
  FAIL: { icon: CircleX, className: 'text-destructive' },
  UNKNOWN: { icon: CircleDashed, className: 'text-muted-foreground' },
}

export interface BuildCompatibilityListProps {
  readonly checks: readonly BuildCompatibilityCheck[]
  /** 抽屉内模块卡已有标题时传 false，避免重复标题占位 */
  readonly heading?: boolean
}

/**
 * 兼容性校验清单。
 *
 * 顶部用通过计数汇总结论，下方以双列紧凑条目列出规则；
 * 卡片与详情抽屉共用同一实现，避免两处对 PASS / UNKNOWN 的口径出现漂移。
 */
export function BuildCompatibilityList({ checks, heading = true }: BuildCompatibilityListProps) {
  const { t } = useTranslation()
  const visibleChecks = visibleCompatibilityChecks(checks)
  const passedCount = visibleChecks.filter((check) => check.status === 'PASS').length
  const attentionChecks = visibleChecks.filter((check) => check.status !== 'PASS')
  const hasFailure = attentionChecks.some((check) => check.status === 'FAIL')

  if (visibleChecks.length === 0) {
    return (
      <div>
        {heading ? (
          <h4 className="mb-2 text-[11px] font-medium text-muted-foreground">
            {t('chat.build.compatibility')}
          </h4>
        ) : null}
        <p className="text-sm text-muted-foreground">{t('chat.build.noChecks')}</p>
      </div>
    )
  }

  const tone = hasFailure ? 'destructive' : attentionChecks.length > 0 ? 'warning' : 'success'

  return (
    <div className="@container flex min-h-0 flex-1 flex-col">
      {heading ? (
        <h4 className="mb-2 text-[11px] font-medium text-muted-foreground">
          {t('chat.build.compatibility')}
        </h4>
      ) : null}

      {/* 汇总圈：数字为通过项数，文案区分「全部通过」与「需要关注」，不只看颜色 */}
      <div
        className={cn(
          'mb-2.5 flex shrink-0 items-center gap-3 rounded-xl px-3 py-2.5',
          tone === 'success' && 'bg-success/10',
          tone === 'warning' && 'bg-warning/10',
          tone === 'destructive' && 'bg-destructive/10',
        )}
      >
        <span
          className={cn(
            'flex size-11 shrink-0 items-center justify-center rounded-full border-2 text-sm font-semibold tabular-nums',
            tone === 'success' && 'border-success/60 text-success',
            tone === 'warning' && 'border-warning/60 text-warning',
            tone === 'destructive' && 'border-destructive/60 text-destructive',
          )}
        >
          {passedCount}/{visibleChecks.length}
        </span>
        <div className="min-w-0">
          <p
            className={cn(
              'text-[13px] font-semibold',
              tone === 'success' && 'text-success',
              tone === 'warning' && 'text-warning',
              tone === 'destructive' && 'text-destructive',
            )}
          >
            {attentionChecks.length === 0
              ? t('chat.build.checksAllPass')
              : t('chat.build.checksAttention', { count: attentionChecks.length })}
          </p>
          <p className="text-[11px] text-muted-foreground">
            {t('chat.build.checksRules', { count: visibleChecks.length })}
          </p>
        </div>
      </div>

      {/* 规则与说明共用一块可滚动区域：内容少时贴顶排，内容多时整体滚动，
          避免规则列表 flex-1 把说明顶到卡片最底部、中间留出大块空白 */}
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto pr-1">
        <ul className="grid grid-cols-1 content-start gap-1.5 @min-[380px]:grid-cols-2">
          {visibleChecks.map((check, index) => {
            const statusIcon = STATUS_ICONS[check.status]
            const StatusIcon = statusIcon.icon
            const pending = isBlockingPending(check)

            return (
              <li
                key={`${check.rule}-${index}`}
                className="flex min-w-0 items-center gap-1.5 rounded-md bg-surface px-2 py-1.5"
                title={check.message ?? check.rule}
              >
                <StatusIcon
                  className={cn('size-3.5 shrink-0', statusIcon.className)}
                  aria-hidden="true"
                />
                <span className="min-w-0 flex-1 text-[12px] leading-snug break-words text-foreground/85">
                  {check.rule}
                </span>
                {check.status !== 'PASS' ? (
                  <Badge
                    className={cn(
                      'shrink-0 border text-[10px] leading-tight',
                      COMPATIBILITY_STATUS_STYLES[check.status],
                    )}
                  >
                    {t(COMPATIBILITY_STATUS_LABEL_KEYS[check.status])}
                  </Badge>
                ) : null}
                {/* 待核验用虚线 + 危险色独立标注，绝不能复用 PASS 的成功色 */}
                {pending ? (
                  <Badge className="shrink-0 border border-dashed border-destructive/50 bg-background px-1 text-[10px] leading-tight text-destructive">
                    {t('chat.build.status.pendingVerification')}
                  </Badge>
                ) : check.riskLevel === 'ADVISORY' ? (
                  <Badge className="shrink-0 border border-border bg-muted px-1 text-[10px] leading-tight text-muted-foreground">
                    {t('chat.build.risk.advisory')}
                  </Badge>
                ) : null}
              </li>
            )
          })}
        </ul>

        {attentionChecks.length > 0 ? (
          <ul className="mt-2.5 space-y-1">
            {attentionChecks.map((check, index) => (
              <li
                key={`${check.rule}-detail-${index}`}
                className="text-[11.5px] leading-relaxed text-muted-foreground"
              >
                <span className="font-medium text-foreground/70">{check.rule}：</span>
                {check.message ?? t(COMPATIBILITY_STATUS_LABEL_KEYS[check.status])}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  )
}
