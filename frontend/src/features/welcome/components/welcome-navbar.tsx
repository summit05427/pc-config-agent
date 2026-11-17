import { useLayoutEffect, useRef } from 'react'
import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { LocaleToggle } from '@/app/layouts/components/locale-toggle'
import { ThemeToggle } from '@/app/layouts/components/theme-toggle'
import { useAuthSessionStore } from '@/features/auth/model/auth-session'
import { ROUTE_PATHS } from '@/routes/paths'
import { env } from '@/shared/lib/env'
import { BrandMark } from '@/shared/ui/brand-mark'

import { gsap, ScrollTrigger } from '../lib/gsap'
import { prefersReducedMotion } from '../lib/motion'
import { WelcomeExploreButton } from './welcome-explore-button'

/** 收缩后的目标宽度：对齐参考稿约 44vw（1920 视口实测 ≈848px），窄屏由 min 兜底 */
const SHRINK_TARGET_PX = 848

const NAV_LINKS = [
  { href: '#manifesto', key: 'welcome.landing.nav.manifesto' },
  { href: '#journey', key: 'welcome.landing.nav.journey' },
  { href: '#features', key: 'welcome.landing.nav.features' },
  { href: '#contact', key: 'welcome.landing.nav.contact' },
] as const

/** 深色导航里的图标按钮配色：落地页固定近黑底，不能沿用主题令牌的正文色 */
const DARK_ICON_BUTTON = 'text-[#eae7e0]/60 hover:bg-white/10 hover:text-[#eae7e0]'

export function WelcomeNavbar() {
  const { t } = useTranslation()
  const navRef = useRef<HTMLElement>(null)
  const isAuthenticated = useAuthSessionStore((state) => state.status === 'authenticated')

  useLayoutEffect(() => {
    const nav = navRef.current
    if (!nav || prefersReducedMotion()) {
      return
    }

    const ctx = gsap.context(() => {
      // 收缩前的自然宽度：向上滚回阈值上方时恢复用
      const naturalWidth = nav.offsetWidth

      /**
       * 一步到位式补间（时间驱动，与滚动位置脱钩）：宽度与背景不透明度同步过渡。
       * maxWidth 起点取当前实测宽度，fromTo 保证任意中途触发都无跳变（overwrite 杀旧补间）。
       */
      const tweenNav = (targetWidth: number, targetBg: string, onComplete?: () => void): void => {
        gsap.fromTo(
          nav,
          { maxWidth: `${nav.offsetWidth}px` },
          {
            maxWidth: `${targetWidth}px`,
            backgroundColor: targetBg,
            duration: 0.55,
            ease: 'power3.out',
            overwrite: true,
            onComplete,
          },
        )
      }

      // 阈值触发（非 scrub）：滚过首屏 50% 的瞬间收缩完成，滚回上方则恢复原宽
      ScrollTrigger.create({
        start: () => window.innerHeight * 0.5,
        invalidateOnRefresh: true,
        onEnter: () => tweenNav(Math.min(SHRINK_TARGET_PX, window.innerWidth - 32), 'rgba(20,20,20,0.88)'),
        onLeaveBack: () =>
          tweenNav(naturalWidth, 'rgba(20,20,20,0.6)', () => nav.style.removeProperty('max-width')),
      })
    }, nav)

    return () => ctx.revert()
  }, [])

  return (
    // 外层只负责 fixed 定位与居中；nav 宽 85%，比 hero 卡略窄并悬浮在卡片之上
    <div className="fixed inset-x-0 top-7 z-50 flex justify-center md:top-9">
      <nav
        ref={navRef}
        className="flex h-12 w-[85%] items-center justify-between rounded-xl border border-white/[0.06] bg-[#141414]/60 px-4 backdrop-blur-md will-change-[max-width] md:px-6"
      >
        <a href="#top" className="flex items-center gap-2.5">
          <BrandMark size="md" />
          <span className="font-serif text-xl text-[#eae7e0]">{env.title}</span>
        </a>

        <section className="hidden items-center gap-8 text-sm text-[#eae7e0]/60 md:flex">
          {NAV_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="transition-colors duration-200 hover:text-[#eae7e0]"
            >
              {t(link.key)}
            </a>
          ))}
        </section>

        <section className="flex items-center gap-3">
          <div className="hidden items-center gap-0.5 sm:flex">
            <ThemeToggle className={DARK_ICON_BUTTON} />
            <LocaleToggle className={DARK_ICON_BUTTON} />
          </div>

          {isAuthenticated ? null : (
            <Link
              to={ROUTE_PATHS.login}
              className="text-sm text-[#eae7e0]/60 transition-colors duration-200 hover:text-[#eae7e0]"
            >
              {t('welcome.landing.nav.login')}
            </Link>
          )}

          <WelcomeExploreButton
            label={
              isAuthenticated
                ? t('welcome.landing.nav.startBuilding')
                : t('welcome.landing.nav.getStarted')
            }
          />
        </section>
      </nav>
    </div>
  )
}
