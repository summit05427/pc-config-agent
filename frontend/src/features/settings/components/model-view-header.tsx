import type { ReactNode } from 'react'
import { ArrowLeft } from 'lucide-react'

import { Button } from '@/shared/ui/button'

export interface ModelViewHeaderProps {
  backLabel: string
  title: string
  description: string
  onBack: () => void
  /** 供应商 logo 等前置标识，由调用方决定是否渲染 */
  leading?: ReactNode
  /** 标题旁的状态徽标 */
  badge?: ReactNode
}

/** 模型与密钥子视图头部：返回、标题、说明与可选标识，三个视图共用同一排版 */
export function ModelViewHeader({
  backLabel,
  title,
  description,
  onBack,
  leading,
  badge,
}: ModelViewHeaderProps) {
  return (
    <div className="flex flex-col gap-4">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="-ml-2 w-fit text-muted-foreground"
        onClick={onBack}
      >
        <ArrowLeft aria-hidden="true" />
        {backLabel}
      </Button>

      <div className="flex items-start gap-3">
        {leading}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-medium tracking-[-0.01em] text-foreground">{title}</h3>
            {badge}
          </div>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{description}</p>
        </div>
      </div>
    </div>
  )
}
