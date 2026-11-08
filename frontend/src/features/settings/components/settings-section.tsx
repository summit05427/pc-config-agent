import type { ReactNode } from 'react'

export interface SettingsSectionProps {
  title: string
  description: string
  /** 标题旁的补充标签，用于区分同一分区的数据口径 */
  badge?: ReactNode
  children: ReactNode
}

/** 设置分区外壳：标题 + 说明 + 内容，所有分区共用同一套排版 */
export function SettingsSection({ title, description, badge, children }: SettingsSectionProps) {
  return (
    <section className="flex flex-col gap-8">
      <header>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-xl font-semibold tracking-[-0.02em] text-foreground">{title}</h2>
          {badge}
        </div>
        <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-muted-foreground">
          {description}
        </p>
      </header>

      {children}
    </section>
  )
}
