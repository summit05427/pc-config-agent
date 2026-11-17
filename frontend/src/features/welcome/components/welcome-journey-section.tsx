import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { Star, TrendingUp } from 'lucide-react'
import { Trans, useTranslation } from 'react-i18next'

import { gsap, ScrollTrigger } from '../lib/gsap'
import { getLenis } from '../lib/smooth-scroll'

const SCROLL_LOCK_CLASS = 'wl-intro-lock'

/**
 * intro 播放期间锁定页面滚动：html.overflow hidden + scrollbar-gutter 占位防布局跳动。
 * Lenis 的输出必须同步冻结（stop）：否则锁定期间滚轮输入会持续累积内部目标值，
 * 解锁瞬间滚动位置会突跳到累积处。
 */
const lockScroll = (): void => {
  document.documentElement.classList.add(SCROLL_LOCK_CLASS)
  getLenis()?.stop()
}

const unlockScroll = (): void => {
  document.documentElement.classList.remove(SCROLL_LOCK_CLASS)
  getLenis()?.start()
}

/** 同步瞬移滚动到拆卡区顶部：Lenis 接管后原生 scrollTo 会被其内部目标值弹回 */
const jumpToTop = (root: HTMLElement): void => {
  const targetY = Math.round(root.getBoundingClientRect().top + window.scrollY)
  const lenis = getLenis()

  if (lenis) {
    lenis.scrollTo(targetY, { immediate: true, force: true })
  } else {
    window.scrollTo(0, targetY)
  }
}

interface JourneyCardProps {
  index: number
  side: 'left' | 'center' | 'right'
  /** 未悬浮时的堆叠层级：中片压左片、右片压中片，悬浮时统一提到最上 */
  baseZClassName: string
  hoveredIndex: number | null
  onHoverChange: (index: number | null) => void
  faceClassName: string
  descriptionClassName: string
  icon: ReactNode
  titleTop: string
  titleBottom: string
  description: string
}

/** 翻转后的内容面：悬浮时自身提亮放大，其余卡压暗（与原稿一致的聚焦效果） */
function JourneyCard({
  index,
  side,
  baseZClassName,
  hoveredIndex,
  onHoverChange,
  faceClassName,
  descriptionClassName,
  icon,
  titleTop,
  titleBottom,
  description,
}: JourneyCardProps) {
  const isHovered = hoveredIndex === index
  const isDimmed = hoveredIndex !== null && !isHovered

  return (
    <div
      className={`wl-slice wl-slice-${side} ${isHovered ? 'z-30' : baseZClassName}`}
      onMouseEnter={() => onHoverChange(index)}
      onMouseLeave={() => onHoverChange(null)}
    >
      <div className={`wl-face wl-face-front wl-face-pos-${index}`} />
      <div
        className={`wl-face wl-face-back flex flex-col ${faceClassName} ${
          isHovered ? 'is-hovered' : ''
        } ${isDimmed ? 'is-dimmed' : ''}`}
      >
        {icon}
        <h3 className="mt-auto text-[clamp(1.3rem,1.8vw,1.75rem)] leading-snug font-medium">
          {titleTop}
          <br />
          {titleBottom}
        </h3>
        <p className={`mt-3 text-xs md:text-sm ${descriptionClassName}`}>{description}</p>
      </div>
    </div>
  )
}

export function WelcomeJourneySection() {
  const { t } = useTranslation()
  const rootRef = useRef<HTMLElement>(null)
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)

  useLayoutEffect(() => {
    const root = rootRef.current
    if (!root) {
      return
    }

    let hasPlayed = false
    let introTl: gsap.core.Timeline | null = null

    const ctx = gsap.context(() => {
      /**
       * 拆卡 intro（时间驱动，非 scrub）：
       * 阶段1 完整卡缩小 → 阶段2 标题从下往上滑出 → 阶段3 裂开三等分缝隙 →
       * 阶段4 三片各自绕 Y 轴翻 180° 露出内容面，同时散开归位扇形倾斜。
       */
      const wrap = root.querySelector<HTMLElement>('.wl-card-wrap')
      const wrapWidth = wrap?.offsetWidth ?? 1000

      // 散开平移只做微量外移（~1% 卡组宽）：交叠主要靠旋转几何，
      // 侧卡绕中心转 12° 后底角自然向内甩出约 42px，与邻卡形成约 30px 交叠
      const spreadX = Math.round(wrapWidth * 0.01)

      // 侧卡倾斜下沉补偿：矩形绕中心倾斜 θ 后最高点上移，给两侧卡等量下移，
      // 使三张卡的最高点落在同一水平线（卡组纵横比 9/4 → 单卡 3:4）
      const sliceWidth = wrapWidth / 3
      const sliceHeight = (wrapWidth * 4) / 9
      const tiltRad = (12 * Math.PI) / 180
      const tiltRise = Math.round(
        (sliceWidth / 2) * Math.sin(tiltRad) - (sliceHeight / 2) * (1 - Math.cos(tiltRad)),
      )

      introTl = gsap
        .timeline({
          paused: true,
          defaults: { ease: 'power2.inOut' },
          onComplete: () => {
            hasPlayed = true
            unlockScroll()
          },
        })
        .fromTo('.wl-card-wrap', { scale: 1.15 }, { scale: 0.95, duration: 0.55 })
        // 标题在卡片缩放到目标尺寸后滑出；immediateRender 让它在挂载时就隐藏，
        // 直到 intro 播放到该位置才显形
        .from(
          '.wl-split-heading',
          { y: 48, opacity: 0, duration: 0.55, ease: 'power3.out', immediateRender: true },
          '>',
        )
        // 裂开瞬间切换渲染源：整卡贴图（零接缝）→ 三片贴图（随翻转位移）
        .set('.wl-artwork-whole', { autoAlpha: 0 }, '+=0.12')
        .to('.wl-slice-left', { x: -14, duration: 0.4 }, '<')
        .to('.wl-slice-right', { x: 14, duration: 0.4 }, '<')
        .to(
          '.wl-slice-left',
          { rotationY: 180, x: -spreadX, y: tiltRise, rotationZ: -12, duration: 0.85 },
          '+=0.1',
        )
        .to('.wl-slice-center', { rotationY: -180, duration: 0.85 }, '<0.08')
        .to(
          '.wl-slice-right',
          { rotationY: -180, x: spreadX, y: tiltRise, rotationZ: 12, duration: 0.85 },
          '<',
        )

      // 减少动效偏好 / 加载时已越过该区（刷新恢复、深链接）：直接呈现终态扇形
      const isPastSection = root.getBoundingClientRect().top <= 0
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || isPastSection) {
        introTl.progress(1)
        return
      }

      // 首次进入自动播放一次并锁滚动。触发点提前 2px：规避滚动恰停在边界时的浮点误差
      ScrollTrigger.create({
        trigger: root,
        start: 'top top+=2',
        onEnter: () => {
          // 快速滚动会越过触发点才触发：先同步校正回区块顶对齐，再锁滚动
          if (hasPlayed || introTl?.isActive()) {
            return
          }
          hasPlayed = true
          jumpToTop(root)
          lockScroll()
          introTl?.timeScale(1).play(0)
        },
      })

      // 向上滚离该区 120px 后反向播放（1.6 倍速）：翻转→拼接→放大回到闭合整卡态。
      // 反向期间不锁滚动（用户本就向上离开）；完成后复位，再次向下进入会重播
      ScrollTrigger.create({
        trigger: root,
        start: 'top top+=120',
        onLeaveBack: () => {
          if (!hasPlayed || introTl?.isActive()) {
            return
          }
          hasPlayed = false
          introTl?.timeScale(1.6).reverse()
        },
      })
    }, root)

    return () => {
      // 卸载时必须解锁，避免把全局滚动锁死
      unlockScroll()
      ctx.revert()
    }
  }, [])

  return (
    // 拆卡叙事区：滚动进入后自动播放 intro，pt-24 让标题避开悬浮导航
    <section
      id="journey"
      ref={rootRef}
      className="wl-dots relative z-10 flex h-screen flex-col items-center justify-center overflow-hidden bg-[#0a0a0a] px-6 pt-24"
    >
      <h2 className="wl-split-heading mb-10 text-center font-serif text-[clamp(1.75rem,3vw,2.75rem)] leading-[1.15] font-medium text-[#eae7e0]">
        <Trans i18nKey="welcome.landing.journey.title" components={{ em: <em /> }} />
      </h2>

      {/* 3D 舞台：perspective 必须写在父容器；三片各承载卡面的 1/3（9/4 → 单卡 3:4 竖卡） */}
      <div className="wl-card-wrap relative aspect-[9/4] w-[min(1000px,72vw)] [perspective:1400px]">
        {/* 整卡贴图覆盖层：闭合态唯一渲染源，裂开瞬间由 intro 隐藏 */}
        <div className="wl-artwork-whole pointer-events-none absolute inset-0 z-40 rounded-[1.5rem]" />

        <JourneyCard
          index={0}
          side="left"
          baseZClassName=""
          hoveredIndex={hoveredIndex}
          onHoverChange={setHoveredIndex}
          faceClassName="bg-[linear-gradient(160deg,#f2f2f0_0%,#c9cac6_45%,#949693_100%)] p-6 text-[#262626] md:p-7"
          descriptionClassName="text-black/60"
          icon={<TrendingUp className="size-6" />}
          titleTop={t('welcome.landing.journey.cards.zero.titleTop')}
          titleBottom={t('welcome.landing.journey.cards.zero.titleBottom')}
          description={t('welcome.landing.journey.cards.zero.description')}
        />

        <JourneyCard
          index={1}
          side="center"
          baseZClassName="z-10"
          hoveredIndex={hoveredIndex}
          onHoverChange={setHoveredIndex}
          faceClassName="bg-[radial-gradient(120%_120%_at_30%_20%,#e64434_0%,#b3251e_55%,#7e150f_100%)] p-6 text-white md:p-7"
          descriptionClassName="text-white/70"
          icon={
            <span className="flex gap-1.5">
              <span className="size-1.5 rounded-full border border-white/70" />
              <span className="size-1.5 rounded-full border border-white/70" />
              <span className="size-1.5 rounded-full border border-white/70" />
            </span>
          }
          titleTop={t('welcome.landing.journey.cards.scale.titleTop')}
          titleBottom={t('welcome.landing.journey.cards.scale.titleBottom')}
          description={t('welcome.landing.journey.cards.scale.description')}
        />

        <JourneyCard
          index={2}
          side="right"
          baseZClassName="z-20"
          hoveredIndex={hoveredIndex}
          onHoverChange={setHoveredIndex}
          faceClassName="border border-white/10 bg-[linear-gradient(165deg,#232323_0%,#151515_55%,#0f0f0f_100%)] p-6 text-[#f5f5f5] md:p-7"
          descriptionClassName="text-white/60"
          icon={<Star className="size-6" />}
          titleTop={t('welcome.landing.journey.cards.quick.titleTop')}
          titleBottom={t('welcome.landing.journey.cards.quick.titleBottom')}
          description={t('welcome.landing.journey.cards.quick.description')}
        />
      </div>
    </section>
  )
}
