import { Check, Monitor, Moon, Sun } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { selectResolvedTheme, useAppStore } from '@/app/stores/app-store'
import type { ThemeMode } from '@/shared/types/app'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/utils'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/shared/ui/dropdown-menu'

/** 主题选项顺序固定为「浅色 → 深色 → 跟随系统」，与设置页的语义一致 */
const THEME_OPTIONS: readonly { value: ThemeMode; labelKey: string }[] = [
    { value: 'light', labelKey: 'theme.light' },
    { value: 'dark', labelKey: 'theme.dark' },
    { value: 'system', labelKey: 'theme.system' },
]

export interface ThemeToggleProps {
    /** 覆盖触发器按钮配色：落地页为固定近黑底，需要深色适配 */
    className?: string
}

/**
 * 主题切换。
 *
 * 批次一只写入 store 并立即生效，Vue 基线中的圆形扩散转场依赖 View Transitions，
 * 留到后续批次在主题 Hook 中统一实现，避免这里出现两套切换逻辑。
 */
export function ThemeToggle({ className }: ThemeToggleProps) {
    const { t } = useTranslation()
    const theme = useAppStore((state) => state.theme)
    const resolvedTheme = useAppStore(selectResolvedTheme)
    const setTheme = useAppStore((state) => state.setTheme)

    // system 模式显示显示器图标，其余模式显示当前实际生效的明暗图标
    const CurrentIcon = theme === 'system' ? Monitor : resolvedTheme === 'dark' ? Moon : Sun

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className={cn(className)} aria-label={t('theme.switch')}>
                    <CurrentIcon className="size-4" />
                </Button>
            </DropdownMenuTrigger>

            <DropdownMenuContent align="end" className="w-36">
                {THEME_OPTIONS.map((option) => (
                    <DropdownMenuItem key={option.value} onSelect={() => setTheme(option.value)}>
                        <span>{t(option.labelKey)}</span>
                        {theme === option.value ? <Check className="ml-auto size-4" /> : null}
                    </DropdownMenuItem>
                ))}
            </DropdownMenuContent>
        </DropdownMenu>
    )
}
