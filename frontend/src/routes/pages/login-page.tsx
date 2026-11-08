import { useTranslation } from 'react-i18next'
import { useNavigate, useSearch } from '@tanstack/react-router'

import { LoginForm } from '@/features/auth/components/login-form'
import { LoginHero } from '@/features/auth/components/login-hero'
import { useAuthSessionStore } from '@/features/auth/model/auth-session'
import type { LoginFormValues } from '@/features/auth/model/login-schema'
import { ROUTE_PATHS } from '@/routes/paths'
import { env } from '@/shared/lib/env'
import { BrandMark } from '@/shared/ui/brand-mark'
import { LocaleToggle } from '@/app/layouts/components/locale-toggle'
import { ThemeToggle } from '@/app/layouts/components/theme-toggle'

/**
 * 只允许站内绝对路径回跳，避免 redirect 参数被用作开放重定向。
 * 与登录页、401 跳转两处入口共用同一条判定规则。
 */
const isSafeRedirect = (value: string | undefined): value is string =>
    typeof value === 'string' &&
    value.startsWith('/') &&
    !value.startsWith('//') &&
    !value.startsWith(ROUTE_PATHS.login)

/** 登录页：左栏说明、右栏表单；成功后按安全回跳地址回到原页面 */
export function LoginPage() {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const search = useSearch({ from: '/login' })

    const handleSubmit = async (values: LoginFormValues): Promise<void> => {
        await useAuthSessionStore.getState().login({
            username: values.username,
            password: values.password,
        })
        const target = isSafeRedirect(search.redirect) ? search.redirect : ROUTE_PATHS.chatNew
        await navigate({ href: target, replace: true })
    }

    return (
        <div className="grid min-h-dvh bg-background text-foreground lg:grid-cols-[1.05fr_1fr]">
            <LoginHero />

            <main className="relative flex items-center justify-center px-4 py-12 sm:px-8">
                <div className="absolute right-3 top-3 flex items-center gap-0.5">
                    <ThemeToggle />
                    <LocaleToggle />
                </div>

                <div className="w-full max-w-[21rem]">
                    <div className="mb-8 flex items-center gap-2.5 lg:hidden">
                        <BrandMark />
                        <span className="brand-wordmark">{env.title}</span>
                    </div>

                    <h2 className="text-xl font-semibold tracking-[-0.01em]">{t('login.title')}</h2>
                    <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                        {t('login.description')}
                    </p>

                    <LoginForm onSubmit={handleSubmit} />
                </div>
            </main>
        </div>
    )
}
