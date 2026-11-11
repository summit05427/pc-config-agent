import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowUp, Check, SlidersHorizontal, Sparkles } from 'lucide-react'

import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/utils'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/ui/popover'

import { buildQuickPrompt, QUICK_PROMPT_GROUPS, type QuickPromptGroup } from '../model/quick-prompt'

export interface QuickPromptPickerProps {
  /** 确认后把组合好的需求描述交给调用方（写回输入框，不直接发送） */
  readonly onConfirm: (prompt: string) => void
}

/**
 * 结构化需求选择面板。
 *
 * 输入框左下角的入口，帮助说不清需求的用户累积勾选条件；确认后生成一段
 * 完整描述写回输入框，由用户决定是否补充后发送。选择状态只存在组件内，
 * 关闭面板不丢失，确认后清空以便下一轮重新组合。
 */
export function QuickPromptPicker({ onConfirm }: QuickPromptPickerProps) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)
  const [selectedIds, setSelectedIds] = useState<ReadonlySet<string>>(() => new Set())

  const toggleOption = useCallback((group: QuickPromptGroup, optionId: string): void => {
    setSelectedIds((previous) => {
      const next = new Set(previous)
      if (next.has(optionId)) {
        next.delete(optionId)
        return next
      }
      // 互斥组先清掉同组旧值，再写入新选项
      if (group.isExclusive) {
        for (const option of group.options) {
          next.delete(option.id)
        }
      }
      next.add(optionId)
      return next
    })
  }, [])

  const handleConfirm = (): void => {
    const prompt = buildQuickPrompt(selectedIds, t)
    if (!prompt) {
      return
    }
    onConfirm(prompt)
    setSelectedIds(new Set())
    setIsOpen(false)
  }

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-muted-foreground"
          aria-label={t('chat.quickPick.trigger')}
        >
          <SlidersHorizontal data-icon="inline-start" />
          <span>{t('chat.quickPick.trigger')}</span>
        </Button>
      </PopoverTrigger>

      {/* 高度跟随可用空间收缩，避免在小视口里溢出屏幕；主体区自己滚动 */}
      <PopoverContent
        side="top"
        align="start"
        sideOffset={8}
        collisionPadding={16}
        aria-label={t('chat.quickPick.title')}
        className="flex max-h-[var(--radix-popover-content-available-height)] w-96 max-w-[calc(100vw-2rem)] flex-col overflow-hidden p-0"
      >
        <header className="flex shrink-0 items-start gap-2.5 border-b border-border px-4 py-3">
          <span className="mt-0.5 inline-flex size-7 items-center justify-center rounded-[var(--cds-radius-btn-md)] bg-muted text-foreground">
            <Sparkles className="size-4" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-foreground">{t('chat.quickPick.title')}</p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {t('chat.quickPick.description')}
            </p>
          </div>
        </header>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-3">
          {QUICK_PROMPT_GROUPS.map((group) => (
            <div key={group.id} role="group" aria-label={t(group.labelKey)}>
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-medium text-muted-foreground">
                  {t(group.labelKey)}
                </span>
                {group.isExclusive ? (
                  <span className="rounded-[var(--cds-radius-btn-xs)] bg-muted px-1 py-px text-xs text-muted-foreground">
                    {t('chat.quickPick.singleSelect')}
                  </span>
                ) : null}
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {group.options.map((option) => {
                  const isSelected = selectedIds.has(option.id)
                  return (
                    <button
                      key={option.id}
                      type="button"
                      aria-pressed={isSelected}
                      onClick={() => toggleOption(group, option.id)}
                      className={cn(
                        'inline-flex h-[var(--control-height-sm)] items-center gap-1 rounded-[var(--cds-radius-btn-xs)] border px-2.5 text-xs outline-none transition-colors duration-150 select-none focus-visible:ring-2 focus-visible:ring-ring/35',
                        isSelected
                          ? 'border-primary bg-primary font-medium text-primary-foreground'
                          : 'border-border bg-surface text-foreground hover:border-ring/40 hover:bg-muted',
                      )}
                    >
                      {isSelected ? <Check aria-hidden="true" className="size-3" /> : null}
                      {t(option.labelKey)}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>

        <footer className="flex shrink-0 items-center gap-2 border-t border-border bg-surface px-3 py-2.5">
          <span className="pl-1 text-xs text-muted-foreground">
            {t('chat.quickPick.selectedCount', { selected: selectedIds.size })}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="ml-auto text-muted-foreground"
            disabled={selectedIds.size === 0}
            onClick={() => setSelectedIds(new Set())}
          >
            {t('chat.quickPick.clear')}
          </Button>
          <Button type="button" size="sm" disabled={selectedIds.size === 0} onClick={handleConfirm}>
            {t('chat.quickPick.confirm')}
            <ArrowUp data-icon="inline-end" />
          </Button>
        </footer>
      </PopoverContent>
    </Popover>
  )
}
