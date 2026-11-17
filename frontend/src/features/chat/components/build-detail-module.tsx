import type { ComponentType, ReactNode } from 'react'

import { cn } from '@/shared/lib/utils'

export interface BuildDetailModuleProps {
  readonly title: string
  /** 标题左侧图标（lucide-react 组件） */
  readonly icon?: ComponentType<{ className?: string; 'aria-hidden'?: boolean }>
  /** 标题右侧操作区 */
  readonly action?: ReactNode
  readonly className?: string
  readonly bodyClassName?: string
  /** 瀑布入场延迟：逐卡递增，形成自上而下的节奏 */
  readonly delayMs?: number
  readonly children: ReactNode
}

/**
 * 详情抽屉内的统一模块卡：图标标题 + hairline 分隔 + 可滚动内容区。
 *
 * 所有模块共用同一外壳，保证背景、圆角、标题排版一致；
 * 入场只动 opacity/transform，不触发布局抖动。
 */
export function BuildDetailModule({
  title,
  icon: Icon,
  action,
  className,
  bodyClassName,
  delayMs = 0,
  children,
}: BuildDetailModuleProps) {
  return (
    <section
      className={cn(
        'animate-in fade-in-0 flex min-h-0 min-w-0 flex-col overflow-hidden rounded-2xl border border-border/60 bg-surface-raised shadow-sm fill-mode-backwards duration-500 slide-in-from-bottom-2 motion-reduce:animate-none',
        className,
      )}
      style={delayMs > 0 ? { animationDelay: `${delayMs}ms` } : undefined}
    >
      <header className="flex shrink-0 items-center gap-2 border-b border-border/50 px-3.5 py-2">
        {Icon ? (
          <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-clay/10">
            <Icon className="size-3.5 text-clay" aria-hidden />
          </span>
        ) : null}
        <h2 className="min-w-0 truncate text-sm font-semibold text-[var(--cds-orange-500)] dark:text-[var(--cds-orange-250)]">
          {title}
        </h2>
        {action ? <div className="ml-auto flex shrink-0 items-center">{action}</div> : null}
      </header>
      <div className={cn('min-h-0 flex-1 overflow-y-auto px-3.5 py-3', bodyClassName)}>
        {children}
      </div>
    </section>
  )
}
