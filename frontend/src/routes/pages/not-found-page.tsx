import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { ArrowLeft } from 'lucide-react'

import { ROUTE_PATHS } from '@/routes/paths'
import { BrandMark } from '@/shared/ui/brand-mark'
import { Button } from '@/shared/ui/button'

/** 兜底 404：保留品牌标识与返回工作台的入口，避免用户停留在死路 */
export function NotFoundPage() {
    const { t } = useTranslation()

    return (
        <div className="mx-auto flex min-h-dvh max-w-md flex-col items-center justify-center px-6 text-center">
            <BrandMark />
            <p className="mt-5 font-mono text-xs tracking-widest text-muted-foreground">404</p>
            <h1 className="mt-2 font-serif text-xl font-normal text-foreground">
                {t('error.notFound.title')}
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {t('error.notFound.description')}
            </p>
            <Button asChild variant="outline" className="mt-6">
                <Link to={ROUTE_PATHS.chatNew}>
                    <ArrowLeft className="size-3.5" />
                    {t('error.notFound.startChat')}
                </Link>
            </Button>
        </div>
    )
}
