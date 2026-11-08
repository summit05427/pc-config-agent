import { useTranslation } from 'react-i18next'
import { Menu } from 'lucide-react'

import { useAppStore } from '@/app/stores/app-store'
import { Button } from '@/shared/ui/button'

/**
 * 窄屏导航入口。
 *
 * 顶栏移除后用一个悬浮按钮承担抽屉入口：只占左上角一角，不重新引入
 * 贯穿整行的导航条；页面内容用顶部内边距避开它。
 */
export function MobileNavTrigger() {
    const { t } = useTranslation()
    const openMobileNav = useAppStore((state) => state.openMobileNav)

    return (
        <Button
            variant="ghost"
            size="icon-sm"
            aria-label={t('layout.openNav')}
            onClick={openMobileNav}
            className="fixed left-2 top-2 z-40 bg-background/80 text-muted-foreground backdrop-blur-sm md:hidden"
        >
            <Menu className="size-4" />
        </Button>
    )
}
