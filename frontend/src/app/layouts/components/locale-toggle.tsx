import { Check, Languages } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useAppStore } from '@/app/stores/app-store'
import type { AppLocale } from '@/shared/types/app'
import { Button } from '@/shared/ui/button'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/shared/ui/dropdown-menu'

// 语言名称始终用该语言本身展示，方便用户在陌生语言界面里也能识别
const LOCALE_OPTIONS: readonly { value: AppLocale; labelKey: string }[] = [
    { value: 'zh-CN', labelKey: 'locale.zhCN' },
    { value: 'en-US', labelKey: 'locale.enUS' },
]

export function LocaleToggle() {
    const { t } = useTranslation()
    const locale = useAppStore((state) => state.locale)
    const setLocale = useAppStore((state) => state.setLocale)

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" aria-label={t('locale.switch')}>
                    <Languages className="size-4" />
                </Button>
            </DropdownMenuTrigger>

            <DropdownMenuContent align="end">
                {LOCALE_OPTIONS.map((option) => (
                    <DropdownMenuItem key={option.value} onSelect={() => setLocale(option.value)}>
                        <span>{t(option.labelKey)}</span>
                        {locale === option.value ? <Check className="ml-auto size-4" /> : null}
                    </DropdownMenuItem>
                ))}
            </DropdownMenuContent>
        </DropdownMenu>
    )
}
