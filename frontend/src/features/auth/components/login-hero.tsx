import { useTranslation } from 'react-i18next'

import { env } from '@/shared/lib/env'
import { BrandMark } from '@/shared/ui/brand-mark'

const STEP_KEYS = [
    { dotClass: 'bg-primary', titleKey: 'login.heroSteps.context', hintKey: 'login.heroSteps.contextHint' },
    { dotClass: 'bg-primary/70', titleKey: 'login.heroSteps.tools', hintKey: 'login.heroSteps.toolsHint' },
    { dotClass: 'bg-primary/45', titleKey: 'login.heroSteps.result', hintKey: 'login.heroSteps.resultHint' },
] as const

/**
 * 登录页左栏：只说明产品如何工作，不做营销式大标题与装饰性背景。
 * 与表单分离，便于登录页在窄屏下单独隐藏这一栏。
 */
export function LoginHero() {
    const { t } = useTranslation()

    return (
        <aside className="hidden flex-col border-r border-border bg-canvas px-10 py-10 lg:flex">
            <div className="flex items-center gap-2.5">
                <BrandMark />
                <span className="brand-wordmark">{env.title}</span>
            </div>

            <div className="my-auto max-w-md">
                {/* 展示型大标题走衬线：西文用 Anthropic Serif，中文由 Noto Serif SC 接管 */}
                <h1 className="font-serif text-display text-foreground">{t('login.heroTitle')}</h1>
                {/* 副标题同样属于展示型文案，与主标题保持同一字体家族 */}
                <p className="mt-4 font-serif text-base leading-relaxed text-muted-foreground">
                    {t('login.heroDescription')}
                </p>

                <ol className="mt-8">
                    {STEP_KEYS.map((step, index) => (
                        <li key={step.titleKey} className={index === STEP_KEYS.length - 1 ? 'relative flex gap-3' : 'relative flex gap-3 pb-5'}>
                            {index === STEP_KEYS.length - 1 ? null : (
                                <span
                                    className="absolute left-[0.4rem] top-3 h-full w-px bg-border"
                                    aria-hidden="true"
                                />
                            )}
                            <span
                                className={`relative mt-1 size-[0.55rem] shrink-0 rounded-full ring-4 ring-canvas ${step.dotClass}`}
                            />
                            <div>
                                <p className="text-xs font-medium text-foreground">{t(step.titleKey)}</p>
                                <p className="mt-0.5 text-xs text-muted-foreground">{t(step.hintKey)}</p>
                            </div>
                        </li>
                    ))}
                </ol>
            </div>
        </aside>
    )
}
