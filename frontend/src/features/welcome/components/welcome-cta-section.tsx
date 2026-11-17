import { useLayoutEffect, useRef } from 'react'
import { Trans, useTranslation } from 'react-i18next'

import { gsap } from '../lib/gsap'
import { prefersReducedMotion } from '../lib/motion'
import { WelcomeExploreButton } from './welcome-explore-button'

export function WelcomeCtaSection() {
  const { t } = useTranslation()
  const rootRef = useRef<HTMLElement>(null)

  useLayoutEffect(() => {
    const root = rootRef.current
    if (!root || prefersReducedMotion()) {
      return
    }

    const ctx = gsap.context(() => {
      // CTA 卡片随滚动浮入放大（scrub 与滚动进度绑定，复刻参考稿的收尾构图）
      gsap.from('.wl-cta-card', {
        y: 120,
        scale: 0.96,
        ease: 'none',
        scrollTrigger: { trigger: root, start: 'top bottom', end: 'top 15%', scrub: true },
      })

      gsap.from('.wl-cta-reveal', {
        y: 32,
        opacity: 0,
        duration: 0.7,
        stagger: 0.1,
        ease: 'power3.out',
        scrollTrigger: { trigger: '.wl-cta-card', start: 'top 55%' },
      })
    }, root)

    return () => ctx.revert()
  }, [])

  return (
    // 相对 z-10 + 不透明底：盖住常驻底层的 hero；卡片沉底（mt-auto），顶部余量留黑
    <section
      id="contact"
      ref={rootRef}
      className="relative z-10 flex min-h-svh flex-col bg-[#0a0a0a] px-4 pt-10 pb-6 md:px-10"
    >
      <div className="wl-cta-card wl-noise relative mt-auto flex min-h-[70svh] flex-col items-center justify-center overflow-hidden rounded-[2rem] px-6 py-24 text-center">
        <div className="absolute inset-0 bg-[radial-gradient(120%_100%_at_50%_30%,#c2372a_0%,#8f1f1c_50%,#57100e_100%)]" />

        <p className="wl-cta-reveal relative z-10 text-lg text-white/75">
          {t('welcome.landing.cta.eyebrow')}
        </p>
        <h2 className="wl-cta-reveal mt-3 font-serif text-[clamp(2.5rem,5.5vw,4.5rem)] leading-[1.05] font-medium text-[#f5f5f5]">
          <Trans i18nKey="welcome.landing.cta.title" components={{ em: <em /> }} />
        </h2>
        <div className="wl-cta-reveal relative z-10 mt-10">
          <WelcomeExploreButton label={t('welcome.landing.cta.startBuilding')} />
        </div>
      </div>

      <footer className="flex flex-col items-center justify-between gap-2 px-2 pt-6 pb-4 text-xs text-[#eae7e0]/40 sm:flex-row">
        <span>{t('welcome.landing.cta.copyright', { year: new Date().getFullYear() })}</span>
        <span>{t('welcome.landing.cta.brand')}</span>
      </footer>
    </section>
  )
}
