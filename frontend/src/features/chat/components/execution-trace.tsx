import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
    Activity,
    AlertCircle,
    Check,
    ChevronRight,
    CircleSlash,
    Loader2,
    type LucideIcon,
} from 'lucide-react'

import { formatDuration, formatElapsedDuration } from '@/shared/lib/format'
import { cn } from '@/shared/lib/utils'

import type { RuntimeToolStep, ToolStepStatus } from '../runtime/types'

interface StatusMeta {
    readonly icon: LucideIcon
    readonly labelKey: string
    readonly toneClass: string
}

const STATUS_META: Record<ToolStepStatus, StatusMeta> = {
    running: { icon: Loader2, labelKey: 'chat.trace.running', toneClass: 'text-muted-foreground' },
    done: { icon: Check, labelKey: 'chat.trace.done', toneClass: 'text-muted-foreground' },
    stopped: {
        icon: CircleSlash,
        labelKey: 'chat.trace.stopped',
        toneClass: 'text-muted-foreground',
    },
    error: { icon: AlertCircle, labelKey: 'chat.trace.failed', toneClass: 'text-destructive' },
}

const DOT_CLASS: Record<ToolStepStatus, string> = {
    running: 'bg-clay',
    done: 'bg-muted-foreground/60',
    stopped: 'bg-muted-foreground/60',
    error: 'bg-destructive',
}

const sumDuration = (steps: readonly RuntimeToolStep[]): number =>
    steps.reduce((total, step) => {
        if (!step.startedAt || !step.finishedAt || step.finishedAt < step.startedAt) {
            return total
        }
        return total + (step.finishedAt - step.startedAt)
    }, 0)

interface TraceStepProps {
    readonly step: RuntimeToolStep
    readonly isExpanded: boolean
    readonly onToggle: (stepId: string) => void
}

/** 单个工具步骤：状态、耗时与可展开的参数/结果 */
function TraceStep({ step, isExpanded, onToggle }: TraceStepProps) {
    const { t } = useTranslation()
    const meta = STATUS_META[step.status]
    const StatusIcon = meta.icon
    const duration = formatDuration(step.startedAt, step.finishedAt)
    const hasDetail = Boolean(step.args || step.result)

    return (
        <li className="relative py-1">
            <span
                className={cn(
                    'absolute -left-[1.28rem] top-[0.72rem] size-[5px] rounded-full ring-4 ring-background',
                    DOT_CLASS[step.status],
                )}
                aria-hidden="true"
            />

            <button
                type="button"
                className="flex w-full items-center gap-2 rounded-md px-1.5 py-0.5 text-left transition-colors hover:bg-muted disabled:cursor-default disabled:hover:bg-transparent"
                disabled={!hasDetail}
                aria-expanded={isExpanded}
                onClick={() => onToggle(step.id)}
            >
                <StatusIcon
                    className={cn(
                        'size-3.5 shrink-0',
                        meta.toneClass,
                        step.status === 'running' && 'animate-spin',
                    )}
                />
                <span className="truncate font-mono text-xs text-foreground">{step.name}</span>
                <span className={cn('shrink-0 text-[0.6875rem]', meta.toneClass)}>
                    {t(meta.labelKey)}
                </span>
                {duration ? (
                    <span className="tabular shrink-0 text-[0.6875rem] text-muted-foreground">
                        {duration}
                    </span>
                ) : null}
                {hasDetail ? (
                    <ChevronRight
                        className={cn(
                            'ml-1 size-3.5 shrink-0 text-muted-foreground/70 transition-transform',
                            isExpanded && 'rotate-90',
                        )}
                        aria-hidden="true"
                    />
                ) : null}
            </button>

            {isExpanded ? (
                <div className="mt-1 space-y-1.5 pb-1 pl-5">
                    {step.args ? (
                        <div>
                            <p className="mb-1 text-[0.6875rem] text-muted-foreground">
                                {t('chat.trace.arguments')}
                            </p>
                            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md border border-code-border bg-code-bg p-2 font-mono text-[0.6875rem] leading-relaxed text-code-foreground">
                                {step.args}
                            </pre>
                        </div>
                    ) : null}
                    {step.result ? (
                        <div>
                            <p className="mb-1 text-[0.6875rem] text-muted-foreground">
                                {t('chat.trace.result')}
                            </p>
                            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md border border-code-border bg-code-bg p-2 font-mono text-[0.6875rem] leading-relaxed text-code-foreground">
                                {step.result}
                            </pre>
                        </div>
                    ) : null}
                    {!step.result && step.status === 'running' ? (
                        <p className="text-[0.6875rem] text-muted-foreground">
                            {t('chat.trace.awaitingResult')}
                        </p>
                    ) : null}
                </div>
            ) : null}
        </li>
    )
}

export interface ExecutionTraceProps {
    readonly steps: readonly RuntimeToolStep[]
    /** 消息仍在生成时保持展开，让用户看到当前步骤而不是空回答 */
    readonly live?: boolean
}

/**
 * 工具执行轨迹。
 *
 * 默认展开规则由渲染期推导而不是 effect 同步：生成结束时长轨迹自动收起，
 * 短轨迹保持展开；用户手动切换后以其选择为准，避免每帧重置。
 */
export function ExecutionTrace({ steps, live = false }: ExecutionTraceProps) {
    const { t } = useTranslation()
    const [userOpen, setUserOpen] = useState<boolean | null>(null)
    const [expandedStepId, setExpandedStepId] = useState<string | null>(null)

    if (steps.length === 0) {
        return null
    }

    const isOpen = userOpen ?? (live || steps.length <= 2)
    const totalDuration = formatElapsedDuration(sumDuration(steps))

    const toggleStep = (stepId: string): void => {
        setExpandedStepId((current) => (current === stepId ? null : stepId))
    }

    return (
        <div>
            <button
                type="button"
                className="inline-flex h-7 items-center gap-1.5 rounded-md px-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                aria-expanded={isOpen}
                onClick={() => setUserOpen(!isOpen)}
            >
                <Activity className={cn('size-3.5', live && 'text-clay')} />
                <span className="font-medium">{t('chat.trace.title')}</span>
                <span className="tabular">{t('chat.trace.stepCount', { count: steps.length })}</span>
                {live ? (
                    <span className="text-muted-foreground">{t('chat.trace.inProgress')}</span>
                ) : totalDuration ? (
                    <span className="tabular">{totalDuration}</span>
                ) : null}
                <ChevronRight
                    className={cn('size-3.5 transition-transform', isOpen && 'rotate-90')}
                    aria-hidden="true"
                />
            </button>

            {isOpen ? (
                <ol className="ml-[0.45rem] mt-1 space-y-0 border-l border-border pl-3">
                    {steps.map((step) => (
                        <TraceStep
                            key={step.id}
                            step={step}
                            isExpanded={expandedStepId === step.id}
                            onToggle={toggleStep}
                        />
                    ))}
                </ol>
            ) : null}
        </div>
    )
}
