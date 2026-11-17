import { useEffect, useLayoutEffect, useRef, useState, type TransitionEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { gsap, ScrollTrigger } from '../lib/gsap'
import { prefersReducedMotion } from '../lib/motion'
import { getLenis } from '../lib/smooth-scroll'

interface FeatureCard {
  key: string
  no: string
  /** 渐变背景：首页红/蓝/青/紫配色体系内的 Tailwind 任意值类 */
  gradient: string
}

/** 轮播卡片：承接产品核心能力清单，六张刚好走满一轮 */
const CARDS: readonly FeatureCard[] = [
  {
    key: 'build',
    no: '(01)',
    gradient: 'bg-[radial-gradient(120%_120%_at_30%_20%,#d8402f_0%,#a52320_55%,#651210_100%)]',
  },
  {
    key: 'preview',
    no: '(02)',
    gradient: 'bg-[radial-gradient(120%_120%_at_30%_20%,#60a5fa_0%,#2563eb_55%,#1e3a8a_100%)]',
  },
  {
    key: 'matching',
    no: '(03)',
    gradient: 'bg-[radial-gradient(120%_120%_at_30%_20%,#2dd4bf_0%,#0d9488_55%,#115e59_100%)]',
  },
  {
    key: 'bottleneck',
    no: '(04)',
    gradient: 'bg-[radial-gradient(120%_120%_at_30%_20%,#8b5cf6_0%,#6d28d9_55%,#4c1d95_100%)]',
  },
  {
    key: 'price',
    no: '(05)',
    gradient: 'bg-[radial-gradient(120%_120%_at_30%_20%,#ff7a5c_0%,#e64434_45%,#7e150f_100%)]',
  },
  {
    key: 'upgrade',
    no: '(06)',
    gradient: 'bg-[linear-gradient(165deg,#2e2e2e_0%,#181818_55%,#0f0f0f_100%)]',
  },
]

/**
 * 渲染列表复制三份：轨道起点向左错开一份（见样式 --wl-loop-steps），
 * 使弧形窗口左右两侧始终有卡片延伸出屏；offset 在一个 CARDS.length 区间内循环，
 * 任一方向走满一份即可无感重置。
 */
const RENDER_CARDS = [...CARDS, ...CARDS, ...CARDS]

/** 自动轮播节奏与单步过渡时长（间隔须大于过渡时长，避免步进叠步） */
const STEP_INTERVAL_MS = 2000
const STEP_TRANSITION_MS = 650

export function WelcomeFeatureSection() {
  const { t } = useTranslation()
  const rootRef = useRef<HTMLElement>(null)
  const bannerRef = useRef<HTMLDivElement>(null)
  const hoveredRef = useRef(false)
  const offsetRef = useRef(0)

  const [offset, setOffset] = useState(0)
  const [withTransition, setWithTransition] = useState(true)

  useEffect(() => {
    const banner = bannerRef.current
    if (!banner || prefersReducedMotion()) {
      return
    }

    // 步进锁与状态镜像都放在 effect 内：滚动/自动轮播共用同一份，不会因重渲染丢失
    let isStepping = false
    let stepLockTimer = 0
    let frameId = 0

    const changeOffset = (next: number): void => {
      offsetRef.current = next
      setOffset(next)
    }

    const applyStep = (delta: number): void => {
      isStepping = true
      window.clearTimeout(stepLockTimer)
      stepLockTimer = window.setTimeout(() => {
        isStepping = false
      }, STEP_TRANSITION_MS)
      changeOffset(offsetRef.current + delta)
    }

    /** 步进分流：后台标签页跳过；回退到起点时先无感瞬移到循环末端再正常回退一步 */
    const stepBy = (delta: number): void => {
      if (isStepping || document.hidden) {
        return
      }

      if (delta < 0 && offsetRef.current === 0) {
        isStepping = true
        setWithTransition(false)
        changeOffset(CARDS.length)
        frameId = requestAnimationFrame(() => {
          frameId = requestAnimationFrame(() => {
            setWithTransition(true)
            isStepping = false
            applyStep(-1)
          })
        })
        return
      }

      applyStep(delta)
    }

    // 悬浮暂停只作用于自动轮播；滚轮步进不受悬浮影响
    const timer = window.setInterval(() => {
      if (!hoveredRef.current) {
        stepBy(1)
      }
    }, STEP_INTERVAL_MS)

    /**
     * 滚轮切卡：下滚下一张、上滚上一张。
     * 参考稿会 preventDefault 把滚轮完全绑给轮播，但展示带几乎满宽，指针落在带上时
     * 页面会被彻底卡住、无法继续向下浏览；这里保留切卡但不吞滚动事件，
     * 用户既能浏览卡片，也能正常离开该区块（Lenis 同理，不加 data-lenis-prevent）。
     */
    const onWheel = (event: WheelEvent): void => {
      if (Math.abs(event.deltaY) < Math.abs(event.deltaX)) {
        return
      }
      stepBy(event.deltaY > 0 ? 1 : -1)
    }
    banner.addEventListener('wheel', onWheel, { passive: true })

    return () => {
      window.clearInterval(timer)
      window.clearTimeout(stepLockTimer)
      cancelAnimationFrame(frameId)
      banner.removeEventListener('wheel', onWheel)
    }
  }, [])

  useLayoutEffect(() => {
    const root = rootRef.current
    if (!root || prefersReducedMotion()) {
      return
    }

    let isDisposed = false

    const ctx = gsap.context(() => {
      /**
       * 吸附完整展示：顶边越过视口 85% 线时平滑吸附对齐区块顶（上下方向进入都吸附），
       * 保证到达该区时轮播带完整入镜。
       */
      const alignToSection = (): void => {
        const targetY = window.scrollY + root.getBoundingClientRect().top
        const lenis = getLenis()

        if (lenis) {
          lenis.scrollTo(targetY, { duration: 0.9, lock: true })
        } else {
          window.scrollTo({ top: targetY, behavior: 'smooth' })
        }
      }

      ScrollTrigger.create({
        trigger: root,
        start: 'top 85%',
        onEnter: alignToSection,
        onEnterBack: alignToSection,
      })

      // 标题与轮播带入场
      gsap.from('.wl-features-line', {
        y: 56,
        opacity: 0,
        duration: 0.85,
        stagger: 0.12,
        ease: 'power3.out',
        scrollTrigger: { trigger: '.wl-features-heading', start: 'top 82%' },
      })

      gsap.from('.wl-carousel-banner', {
        opacity: 0,
        y: 40,
        duration: 0.9,
        ease: 'power3.out',
        scrollTrigger: { trigger: '.wl-carousel-banner', start: 'top 85%' },
      })

      // webfont 晚于 load 事件就绪会改变文本排版高度，导致 ScrollTrigger 触发位置失准
      void document.fonts?.ready.then(() => {
        if (!isDisposed) {
          ScrollTrigger.refresh()
        }
      })
    }, root)

    return () => {
      isDisposed = true
      ctx.revert()
    }
  }, [])

  const handleTransitionEnd = (event: TransitionEvent<HTMLDivElement>): void => {
    // 只关心轨道自身的位移过渡，子元素的过渡不参与重置
    if (event.target !== event.currentTarget || offsetRef.current < CARDS.length) {
      return
    }

    // 走满一轮：先关过渡瞬移回 0（渲染列表已复制、视觉无差），再于下下帧恢复过渡
    setWithTransition(false)
    const next = offsetRef.current - CARDS.length
    offsetRef.current = next
    setOffset(next)
    requestAnimationFrame(() => {
      requestAnimationFrame(() => setWithTransition(true))
    })
  }

  const trackStyle = {
    transform: `translateX(calc(${offset} * (var(--wl-card-w) + var(--wl-card-gap)) * -1))`,
    transition: withTransition
      ? `transform ${STEP_TRANSITION_MS}ms cubic-bezier(0.22, 1, 0.36, 1)`
      : 'none',
  }

  return (
    // 相对 z-10 + 不透明底：hero sticky 常驻底层，此区须盖在其上
    <section
      id="features"
      ref={rootRef}
      className="wl-dots relative z-10 flex min-h-screen flex-col justify-end overflow-hidden bg-[#0a0a0a] px-4 pt-16 pb-10 md:px-10 md:pt-20 md:pb-14"
    >
      <h2 className="wl-features-heading mx-auto mt-10 mb-0 max-w-3xl text-center font-serif text-[clamp(1.5rem,2.6vw,2.25rem)] leading-tight font-medium text-[#eae7e0]">
        <span className="wl-features-line">{t('welcome.landing.features.heading')}</span>
      </h2>

      {/* 椭圆弧形展示带：SVG mask 裁出中部外凸的窗口，卡片沿窗口自动/滚轮步进。
          全屏宽必须显式声明 w-screen，ml calc 让左右边界精确贴合视口 */}
      <div
        ref={bannerRef}
        className="wl-carousel-banner relative ml-[calc(50%-50vw)] w-screen"
        onMouseEnter={() => {
          hoveredRef.current = true
        }}
        onMouseLeave={() => {
          hoveredRef.current = false
        }}
      >
        {/* 氛围底光：窗口后方一团极低透明度暖光，随 mask 一起被裁成椭圆 */}
        <div className="wl-banner-glow pointer-events-none absolute inset-0" aria-hidden="true" />

        <div className="wl-track" style={trackStyle} onTransitionEnd={handleTransitionEnd}>
          {RENDER_CARDS.map((card, index) => (
            <article
              key={`${card.key}-${index}`}
              className={`wl-card wl-noise relative flex flex-col justify-between overflow-hidden p-5 md:p-6 ${card.gradient}`}
            >
              <div className="relative z-10 flex items-center justify-between gap-3">
                <span className="text-xs text-white/65">
                  {t(`welcome.landing.features.cards.${card.key}.caption`)}
                </span>
                <span className="text-xs text-white/40 tabular-nums">{card.no}</span>
              </div>
              <h3 className="relative z-10 font-serif text-[clamp(1.4rem,2.4vw,2.25rem)] leading-tight text-white">
                {t(`welcome.landing.features.cards.${card.key}.title`)}
              </h3>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}
