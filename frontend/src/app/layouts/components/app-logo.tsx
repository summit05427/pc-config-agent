import { Link } from '@tanstack/react-router'

import { env } from '@/shared/lib/env'
import { BrandMark } from '@/shared/ui/brand-mark'
import { ROUTE_PATHS } from '@/routes/paths'

export interface AppLogoProps {
    /** 折叠态只保留图标，文字由 aria-label 补齐 */
    collapsed?: boolean
}

/** 侧栏与抽屉的品牌位，统一进入新对话页，避免品牌标识成为死链接 */
export function AppLogo({ collapsed = false }: AppLogoProps) {
    return (
        <Link
            to={ROUTE_PATHS.chatNew}
            aria-label={env.title}
            className="flex min-w-0 items-center gap-2.5 rounded-md text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
        >
            <BrandMark size="sm" />

            {collapsed ? null : (
                <span className="brand-wordmark truncate">{env.title}</span>
            )}
        </Link>
    )
}
