import { useEffect } from 'react'

import { WelcomeCtaSection } from '@/features/welcome/components/welcome-cta-section'
import { WelcomeFeatureSection } from '@/features/welcome/components/welcome-feature-section'
import { WelcomeHeroSection } from '@/features/welcome/components/welcome-hero-section'
import { WelcomeJourneySection } from '@/features/welcome/components/welcome-journey-section'
import { WelcomeManifestoSection } from '@/features/welcome/components/welcome-manifesto-section'
import { WelcomeNavbar } from '@/features/welcome/components/welcome-navbar'
import { destroySmoothScroll, initSmoothScroll } from '@/features/welcome/lib/smooth-scroll'
import '@/features/welcome/welcome-landing.css'

/**
 * 欢迎页：公开入口，固定暗色方案的整页叙事。
 *
 * 区块顺序即滚动叙事：hero（钉住待覆盖）→ 宣言逐词显白 → 拆卡 → 能力轮播 → CTA/footer。
 * 平滑滚动只在本页启用，卸载时必须销毁，避免把阻尼滚动带到工作区。
 */
export function WelcomePage() {
  useEffect(() => {
    initSmoothScroll()
    return () => destroySmoothScroll()
  }, [])

  return (
    <div className="wl-page min-h-screen bg-[#0a0a0a] text-[#f5f5f5]">
      <WelcomeNavbar />
      <main className="relative">
        <WelcomeHeroSection />
        <WelcomeManifestoSection />
        <WelcomeJourneySection />
        <WelcomeFeatureSection />
        <WelcomeCtaSection />
      </main>
    </div>
  )
}
