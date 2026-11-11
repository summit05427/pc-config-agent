import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { HitlField, HitlInterrupt } from '@/features/sessions/api'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'

export interface HitlPromptProps {
    readonly interrupt: HitlInterrupt
    /** 流式期间禁用提交，避免重复恢复 */
    readonly disabled?: boolean
    readonly onSubmit: (message: string, answer: Record<string, unknown>) => void
}

/**
 * HITL 表单：按服务端 `input_schema` 渲染字段并提交结构化答案。
 *
 * 不新做确认页：表单直接嵌在助手消息里，提交后与普通消息走同一条 SSE 流，
 * 只是多带 `resume` 字段。数值字段在提交前做一次本地校验，服务端仍会再校验。
 */
export function HitlPrompt({ interrupt, disabled = false, onSubmit }: HitlPromptProps) {
    const { t } = useTranslation()
    const [values, setValues] = useState<Record<string, string>>({})
    const [error, setError] = useState<string | null>(null)

    const updateValue = (name: string, value: string): void => {
        setValues((current) => ({ ...current, [name]: value }))
        setError(null)
    }

    const handleSubmit = (): void => {
        const answer: Record<string, unknown> = {}
        const parts: string[] = []

        for (const field of interrupt.fields) {
            const raw = (values[field.name] ?? '').trim()
            if (!raw) {
                if (field.required) {
                    setError(t('chat.hitl.required'))
                    return
                }
                continue
            }
            if (field.type === 'number') {
                const parsed = Number(raw)
                if (!Number.isFinite(parsed) || (field.min !== undefined && parsed < field.min)) {
                    setError(t('chat.hitl.invalidNumber'))
                    return
                }
                answer[field.name] = parsed
            } else {
                answer[field.name] = raw
            }
            parts.push(`${field.label}：${optionLabel(field, raw)}`)
        }

        // 回答文本进入用户气泡；结构化答案由门控节点格式化，两者不互相依赖
        onSubmit(parts.join('；') || interrupt.question, answer)
    }

    return (
        <div className="mt-3 rounded-xl border border-border bg-muted/30 p-4">
            <p className="text-sm leading-relaxed text-foreground">{interrupt.question}</p>

            <div className="mt-3 space-y-3">
                {interrupt.fields.map((field) => (
                    <div key={field.name} className="space-y-1.5">
                        <label
                            className="text-xs font-medium text-muted-foreground"
                            htmlFor={`hitl-${interrupt.interruptId}-${field.name}`}
                        >
                            {field.label}
                            {field.required ? (
                                <span className="ml-0.5 text-destructive" aria-hidden="true">
                                    *
                                </span>
                            ) : null}
                        </label>
                        {renderField(
                            field,
                            interrupt.interruptId,
                            values[field.name] ?? '',
                            updateValue,
                            field.required ? t('chat.hitl.choose') : t('chat.hitl.optional'),
                        )}
                    </div>
                ))}
            </div>

            {error ? (
                <p className="mt-2 text-xs text-destructive" role="alert">
                    {error}
                </p>
            ) : null}

            <div className="mt-3 flex justify-end">
                <Button size="sm" disabled={disabled} onClick={handleSubmit}>
                    {t('chat.hitl.submit')}
                </Button>
            </div>
        </div>
    )
}

function optionLabel(field: HitlField, value: string): string {
    return field.options?.find((option) => option.value === value)?.label ?? value
}

function renderField(
    field: HitlField,
    interruptId: string,
    value: string,
    onChange: (name: string, value: string) => void,
    placeholder: string,
) {
    const inputId = `hitl-${interruptId}-${field.name}`

    if (field.type === 'select') {
        return (
            <select
                id={inputId}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                value={value}
                onChange={(event) => onChange(field.name, event.target.value)}
            >
                <option value="">{placeholder}</option>
                {(field.options ?? []).map((option) => (
                    <option key={option.value} value={option.value}>
                        {option.label}
                    </option>
                ))}
            </select>
        )
    }

    if (field.type === 'radio') {
        return (
            <div className="flex flex-wrap gap-3">
                {(field.options ?? []).map((option) => (
                    <label
                        key={option.value}
                        className="flex cursor-pointer items-center gap-1.5 text-sm"
                    >
                        <input
                            type="radio"
                            name={inputId}
                            value={option.value}
                            checked={value === option.value}
                            onChange={() => onChange(field.name, option.value)}
                        />
                        {option.label}
                    </label>
                ))}
            </div>
        )
    }

    if (field.type === 'number') {
        return (
            <Input
                id={inputId}
                type="number"
                inputMode="numeric"
                min={field.min}
                value={value}
                onChange={(event) => onChange(field.name, event.target.value)}
            />
        )
    }

    return (
        <Input
            id={inputId}
            value={value}
            onChange={(event) => onChange(field.name, event.target.value)}
        />
    )
}
