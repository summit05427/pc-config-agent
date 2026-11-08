import { useTranslation } from 'react-i18next'
import { Link, type ErrorComponentProps } from '@tanstack/react-router'
import { AlertCircle, ArrowLeft } from 'lucide-react'

import { ROUTE_PATHS } from '@/routes/paths'
import { Button } from '@/shared/ui/button'

/**
 * 路由渲染异常兜底。
 *
 * 异常会让 DefaultLayout 整体被替换，因此这里自带全屏版式；
 * 只提供重试与返回工作台两个出口，不展示异常细节，避免把内部堆栈暴露给用户。
 */
export function RouteError({ reset }: ErrorComponentProps) {
    const { t } = useTranslation()

    return (
        <div className="flex min-h-dvh flex-col items-center justify-center gap-3 px-6 text-center">
            <AlertCircle className="size-6 text-destructive" aria-hidden="true" />
            {/* 错误页标题与 404 同属页面级展示标题，统一走衬线 */}
            <h1 className="font-serif text-xl font-normal text-foreground">{t('errors.pageTitle')}</h1>
            <p className="text-sm leading-relaxed text-muted-foreground">{t('errors.pageDescription')}</p>

            <div className="mt-3 flex items-center gap-2">
                <Button onClick={reset}>{t('errors.retry')}</Button>
                <Button asChild variant="outline">
                    <Link to={ROUTE_PATHS.chatNew}>
                        <ArrowLeft className="size-3.5" />
                        {t('errors.startChat')}
                    </Link>
                </Button>
            </div>
        </div>
    )
}
