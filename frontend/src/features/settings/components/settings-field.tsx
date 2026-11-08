import type { ReactNode } from 'react'

import { Label } from '@/shared/ui/label'

export interface SettingsFieldProps {
  id: string
  label: string
  hint?: string
  /** 校验或服务端字段错误；存在时优先于 hint 展示 */
  error?: string
  children: ReactNode
}

/** 表单字段：标签、控件、提示与错误四处固定顺序，避免各分区自行排版 */
export function SettingsField({ id, label, hint, error, children }: SettingsFieldProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id} className="text-sm">
        {label}
      </Label>
      {children}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-xs leading-relaxed text-destructive">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-xs leading-relaxed text-muted-foreground">
          {hint}
        </p>
      ) : null}
    </div>
  )
}
