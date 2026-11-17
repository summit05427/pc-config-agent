import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { gsap } from '../lib/gsap'
import { prefersReducedMotion } from '../lib/motion'

/** 本地时间刷新间隔：复刻参考稿 hero 底部的本地时钟，30s 粒度足够 */
const CLOCK_REFRESH_MS = 30_000

export function WelcomeHeroSection() {
  const { t, i18n } = useTranslation()
  const rootRef = useRef<HTMLElement>(null)
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), CLOCK_REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [])

  useLayoutEffect(() => {
    const root = rootRef.current
    if (!root || prefersReducedMotion()) {
      return
    }

    const ctx = gsap.context(() => {
      // 入场编排（时间驱动一次）：卡片亮起，标题逐行跟进，副标题与 meta 收尾
      const intro = gsap.timeline({ defaults: { ease: 'power3.out' } })
      intro
        .from('.wl-hero-card', { opacity: 0, y: 28, duration: 0.9 })
        .from('.wl-hero-line', { y: 56, opacity: 0, duration: 0.8, stagger: 0.14 }, '-=0.45')
        .from('.wl-hero-sub', { y: 24, opacity: 0, duration: 0.6 }, '-=0.4')
        .from('.wl-hero-meta', { opacity: 0, duration: 0.7 }, '-=0.2')

      /**
       * 幕布覆盖（scrub）：本区 sticky 常驻底层，后续不透明区块从下方滑上覆盖。
       * 前段卡片先缩小露出四周黑底，全程黑幕同步压暗被覆盖中的 hero。
       * 用数值 start/end 而非 trigger 定位：sticky 元素位置随滚动变化会干扰定位计算。
       */
      const cover = gsap.timeline({
        scrollTrigger: { start: 0, end: () => window.innerHeight, scrub: true },
      })
      cover
        .fromTo(
          '.wl-hero-card',
          { scale: 1 },
          { scale: 0.88, duration: 0.45, ease: 'power2.out', immediateRender: false },
          0,
        )
        .to('.wl-hero-dim', { opacity: 0.55, duration: 1, ease: 'none' }, 0)
    }, root)

    return () => ctx.revert()
  }, [])

  return (
    // 底层钉住区：sticky 常驻，后续区块 z-10 不透明，滑上时形成幕布覆盖效果
    <section id="top" ref={rootRef} className="sticky top-0 z-0 h-screen p-3 md:px-10 md:py-5">
      <div className="wl-hero-card wl-noise relative flex h-full flex-col overflow-hidden rounded-[2rem] will-change-transform">
        <div className="absolute inset-0 bg-[radial-gradient(120%_100%_at_50%_18%,#d8402f_0%,#a52320_48%,#651210_100%)]" />

        <div className="relative z-10 flex flex-1 flex-col items-center justify-center px-6 py-24 text-center">
          <h1 className="font-serif text-[clamp(2.5rem,6vw,4.75rem)] leading-[1.05] font-medium text-[#eae7e0]">
            <span className="wl-hero-line block">{t('welcome.landing.hero.lineOne')}</span>
            <span className="wl-hero-line block">{t('welcome.landing.hero.lineTwo')}</span>
          </h1>
          <p className="wl-hero-sub mt-5 text-lg text-[#eae7e0]/75 md:text-xl">
            {t('welcome.landing.hero.sub')}
          </p>
        </div>

        <footer className="wl-hero-meta relative z-10 flex items-center justify-between px-6 pb-6 text-xs text-[#eae7e0]/70 md:px-9 md:pb-8">
          <span>{now.toLocaleTimeString(i18n.language, { hour: 'numeric', minute: '2-digit' })}</span>
          <span>{t('welcome.landing.hero.scroll')}</span>
          <span className="hidden sm:block">{t('welcome.landing.hero.meta')}</span>
        </footer>

        {/* 覆盖退场黑幕：opacity 由 scrub 驱动 */}
        <div className="wl-hero-dim pointer-events-none absolute inset-0 z-20 bg-black opacity-0" />
      </div>
    </section>
  )
}
