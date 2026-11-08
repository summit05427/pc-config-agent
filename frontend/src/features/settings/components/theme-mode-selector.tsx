import { useState } from 'react'
import { Check, Monitor, Moon, Sun, type LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useAppStore } from '@/app/stores/app-store'
import type { ThemeMode } from '@/shared/types/app'
import { cn } from '@/shared/lib/utils'

import { ThemePreviewArt } from './theme-preview-art'

interface ThemeOption {
  value: ThemeMode
  labelKey: string
  icon: LucideIcon
}

const THEME_OPTIONS: readonly ThemeOption[] = [
  { value: 'light', labelKey: 'theme.light', icon: Sun },
  { value: 'dark', labelKey: 'theme.dark', icon: Moon },
  { value: 'system', labelKey: 'theme.system', icon: Monitor },
]

/** 悬浮/聚焦预览与选中态使用同一展开宽度，避免预览与落选时出现跳变 */
const EXPANDED_FLEX_GROW = 1.6
const COLLAPSED_FLEX_GROW = 1

/**
 * 设置页主题选择。
 *
 * 交互借鉴 Vue 版 ThemeToggle：指针或键盘焦点所在的卡片展开，其余卡片压暗虚化；
 * 指针移开后回落到当前选中项。视觉改为 Token 绘制的微缩界面，并保留原生 radio
 * 的键盘方向键、读屏与表单语义。选择直接写入 app-store，立即生效。
 */
export function ThemeModeSelector() {
  const { t } = useTranslation()
  const theme = useAppStore((state) => state.theme)
  const setTheme = useAppStore((state) => state.setTheme)
  const [hoveredTheme, setHoveredTheme] = useState<ThemeMode | null>(null)
  const [focusedTheme, setFocusedTheme] = useState<ThemeMode | null>(null)

  // 选择完成后立即退出悬浮/焦点预览，否则焦点停留会让另外两张卡一直停留在模糊态
  const settlePreview = (): void => {
    setHoveredTheme(null)
    setFocusedTheme(null)
  }

  return (
    <div
      className="flex gap-2"
      role="radiogroup"
      aria-label={t('settings.appearance.theme')}
      onMouseLeave={() => setHoveredTheme(null)}
    >
      {THEME_OPTIONS.map((option) => {
        const isSelected = theme === option.value
        const isPreviewing = hoveredTheme === option.value || focusedTheme === option.value
        const hasPreview = hoveredTheme !== null || focusedTheme !== null
        const isExpanded = isPreviewing || (!hasPreview && isSelected)
        const isDimmed = hasPreview && !isPreviewing
        const flexGrow = isExpanded ? EXPANDED_FLEX_GROW : COLLAPSED_FLEX_GROW

        return (
          <label
            key={option.value}
            data-expanded={isExpanded}
            data-dimmed={isDimmed}
            style={{ flexGrow }}
            onClick={settlePreview}
            className={cn(
              'flex min-w-0 basis-0 cursor-pointer select-none flex-col overflow-hidden rounded-[var(--cds-radius-btn-md)] border bg-surface transition-all duration-500 ease-out motion-reduce:transition-none focus-within:ring-2 focus-within:ring-ring/35',
              isSelected
                ? 'border-clay shadow-[var(--cds-shadow-sm)]'
                : isExpanded
                  ? 'border-border-strong'
                  : 'border-border hover:border-border-strong',
            )}
            onMouseEnter={() => setHoveredTheme(option.value)}
          >
            <input
              type="radio"
              name="settings-theme"
              value={option.value}
              checked={isSelected}
              className="sr-only"
              onChange={() => {
                setTheme(option.value)
                settlePreview()
              }}
              onFocus={() => setFocusedTheme(option.value)}
              onBlur={() =>
                setFocusedTheme((current) => (current === option.value ? null : current))
              }
            />

            <div className="relative h-24 shrink-0 overflow-hidden">
              <div
                className={cn(
                  'absolute inset-0 transition-all duration-500 ease-out motion-reduce:transition-none',
                  isDimmed ? 'scale-105 blur-sm brightness-90' : 'scale-100 blur-none',
                )}
              >
                <ThemePreviewArt variant={option.value} />
              </div>
              <span
                className={cn(
                  'pointer-events-none absolute inset-0 transition-colors duration-500 motion-reduce:transition-none',
                  isDimmed
                    ? 'bg-[var(--cds-gray-900)]/55'
                    : isExpanded
                      ? 'bg-[var(--cds-gray-900)]/10'
                      : 'bg-[var(--cds-gray-900)]/20',
                )}
              />

              {isSelected ? (
                <span className="absolute right-2 top-2 flex size-4 items-center justify-center rounded-full bg-surface text-clay shadow-sm ring-1 ring-clay/40">
                  <Check className="size-2.5" aria-hidden="true" />
                </span>
              ) : null}
            </div>

            <div className="flex h-[var(--control-height-sm)] shrink-0 items-center gap-1.5 border-t border-border/70 px-2">
              {isExpanded ? (
                <option.icon
                  className="size-3.5 shrink-0 text-muted-foreground"
                  aria-hidden="true"
                />
              ) : null}
              <span
                className={cn(
                  'min-w-0 flex-1 truncate text-xs',
                  isSelected
                    ? 'font-medium text-foreground'
                    : isExpanded
                      ? 'text-foreground'
                      : 'text-muted-foreground',
                )}
              >
                {t(option.labelKey)}
              </span>
            </div>
          </label>
        )
      })}
    </div>
  )
}
