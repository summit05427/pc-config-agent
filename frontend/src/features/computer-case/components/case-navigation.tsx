import { useTranslation } from 'react-i18next'
import { CircuitBoard, Cpu, Fan, Gpu, MemoryStick, Zap, type LucideIcon } from 'lucide-react'

import { cn } from '@/shared/lib/utils'

import type { CaseNavItem } from '../hooks/use-computer-case'

/** 标记 id → lucide 图标；未登记的 id 回退为 Cpu，避免渲染空白 */
const NAV_ICONS: Record<string, LucideIcon> = {
  cpu: Cpu,
  radiator: Fan,
  ram: MemoryStick,
  gpu: Gpu,
  motherboard: CircuitBoard,
  psu: Zap,
}

export interface CaseNavigationProps {
  readonly items: readonly CaseNavItem[]
  /** 当前聚焦中的标记 id；null 表示无选中 */
  readonly activeId: string | null
  readonly onSelect: (id: string) => void
}

/**
 * 机箱组件导航：以横向图标菜单替代机箱上的圆点标记。
 *
 * 尺寸全部以 `--nav-unit` 为基准按原稿比例换算，并由容器查询驱动，
 * 因此侧栏拖动、窗口缩放时导航会等比收缩；激活项保持展开并高亮。
 */
export function CaseNavigation({ items, activeId, onSelect }: CaseNavigationProps) {
  const { t } = useTranslation()

  return (
    <nav className="@container mx-auto w-full max-w-[480px]" aria-label={t('chat.casePanel.nav')}>
      <div
        className={cn(
          'mx-auto flex w-fit justify-center',
          'gap-[calc(var(--nav-unit)*0.75)] rounded-[calc(var(--nav-unit)*1.875)]',
          'border border-border bg-linear-to-b from-surface-raised to-surface p-[var(--nav-unit)]',
          'text-foreground shadow-md',
          // 5px 下限保证窄面板下导航不溢出，同时图标仍可辨认
          '[--nav-unit:max(5px,1.1cqi)]',
        )}
      >
        {items.map((item) => {
          const Icon = NAV_ICONS[item.id] ?? Cpu
          const isActive = activeId === item.id

          return (
            <button
              key={item.id}
              type="button"
              className={cn(
                'group/link relative z-[1] inline-flex h-[calc(var(--nav-unit)*6.25)] w-[calc(var(--nav-unit)*8.75)]',
                'shrink-0 origin-left cursor-pointer items-center justify-center overflow-hidden',
                'rounded-[var(--nav-unit)] border-0 bg-transparent p-0 font-[inherit]',
                'text-muted-foreground transition-[width,color] duration-200 ease-in',
                // 滑入的灰色底板：默认移出右侧，展开时平移回位
                "before:absolute before:inset-0 before:block before:translate-x-full before:rounded-[var(--nav-unit)]",
                "before:bg-accent before:transition-transform before:duration-200 before:ease-in before:content-['']",
                'hover:w-[calc(var(--nav-unit)*16.25)] hover:text-foreground hover:before:translate-x-0',
                'focus-visible:w-[calc(var(--nav-unit)*16.25)] focus-visible:text-foreground focus-visible:before:translate-x-0',
                isActive &&
                  'w-[calc(var(--nav-unit)*16.25)] text-ring before:translate-x-0 before:bg-ring/15 before:shadow-[0_0_12px] before:shadow-ring/25 hover:text-ring',
              )}
              aria-label={t('chat.casePanel.focus', { label: item.label })}
              aria-pressed={isActive}
              onClick={() => onSelect(item.id)}
            >
              <span
                aria-hidden="true"
                className="absolute left-[calc(var(--nav-unit)*2.25)] z-10 block size-[calc(var(--nav-unit)*3.5)] shrink-0 [&_svg]:size-full"
              >
                <Icon />
              </span>
              <span
                className={cn(
                  'block w-full translate-x-full text-center whitespace-nowrap opacity-0',
                  'text-[max(11px,calc(var(--nav-unit)*1.75))] leading-none',
                  'transition-[transform,opacity] duration-200 ease-in',
                  '[text-indent:calc(var(--nav-unit)*3.5)]',
                  'group-hover/link:translate-x-0 group-hover/link:opacity-100',
                  'group-focus-visible/link:translate-x-0 group-focus-visible/link:opacity-100',
                  isActive && 'translate-x-0 opacity-100',
                )}
              >
                {item.label}
              </span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}
