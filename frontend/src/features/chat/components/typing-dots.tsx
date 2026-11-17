import { useTranslation } from 'react-i18next'

import { cn } from '@/shared/lib/utils'

const DOT_DELAYS_MS = [0, 160, 320] as const

export interface TypingDotsProps {
  readonly className?: string
}

/**
 * 等待响应的三点跳动动画。
 *
 * 无障碍上仍用 `role="status"` 暴露「正在等待响应」，视觉上不再显示任何
 * 内部工具名或步骤，避免用户看到无意义的执行过程。
 */
export function TypingDots({ className }: TypingDotsProps) {
  const { t } = useTranslation()

  return (
    <span
      role="status"
      aria-label={t('chat.status.waiting')}
      className={cn('inline-flex h-5 items-center gap-1', className)}
    >
      {DOT_DELAYS_MS.map((delay) => (
        <span
          key={delay}
          aria-hidden="true"
          className="typing-dot"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  )
}
