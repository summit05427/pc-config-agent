import { Fragment, useLayoutEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'

import { gsap } from '../lib/gsap'
import { prefersReducedMotion } from '../lib/motion'

/** 品类统计：数字在首次进入该区时自动从 0 滚至目标值（时间驱动，与滚动进度无关） */
const STAT_ITEMS = [
  { key: 'ram', value: 1467 },
  { key: 'ssd', value: 1339 },
  { key: 'case', value: 996 },
  { key: 'cooler', value: 845 },
  { key: 'gpu', value: 718 },
  { key: 'motherboard', value: 684 },
  { key: 'psu', value: 461 },
  { key: 'cpu', value: 130 },
] as const

/** 拉丁词整块保留、中文逐字切分：中文没有词间空格，按空格拆会退化成整段不动的文本 */
const CJK_TOKEN_PATTERN = /[A-Za-z0-9][A-Za-z0-9.&+-]*|[^\sA-Za-z0-9]|\s+/g

interface WordToken {
  text: string
  /** 原文中该词前有空格：中文切词会丢掉空格，需补出内边距，避免「实时3D预览」粘连 */
  hasSpaceBefore: boolean
}

const tokenize = (text: string, isCjk: boolean): WordToken[] => {
  if (!isCjk) {
    return text
      .split(' ')
      .filter(Boolean)
      .map((word) => ({ text: word, hasSpaceBefore: false }))
  }

  const tokens: WordToken[] = []
  let hasSpaceBefore = false

  for (const chunk of text.match(CJK_TOKEN_PATTERN) ?? []) {
    if (/^\s+$/.test(chunk)) {
      hasSpaceBefore = true
      continue
    }
    tokens.push({ text: chunk, hasSpaceBefore })
    hasSpaceBefore = false
  }

  return tokens
}

export function WelcomeManifestoSection() {
  const { t, i18n } = useTranslation()
  const rootRef = useRef<HTMLElement>(null)
  const numberRefs = useRef<(HTMLSpanElement | null)[]>([])

  const isCjk = i18n.language.startsWith('zh')
  const manifestoText = t('welcome.landing.manifesto.text')
  const words = useMemo(() => tokenize(manifestoText, isCjk), [manifestoText, isCjk])

  useLayoutEffect(() => {
    const root = rootRef.current
    if (!root) {
      return
    }

    // 减少动效：直接呈现目标值，不做逐词显白与数字滚动
    if (prefersReducedMotion()) {
      return
    }

    const ctx = gsap.context(() => {
      // 数字滚动前先归零：JSX 里渲染的是终值，避免 CSS 未生效时出现 0 闪烁
      numberRefs.current.forEach((element) => {
        if (element) {
          element.textContent = '0'
        }
      })

      // 文本区：逐词显白（滚动驱动）。加大单词过渡时长使相邻词高亮互相重叠，
      // 观感为连续渐亮而非分词跳变；中文按字推进，节奏需要更密
      gsap.fromTo(
        '.wl-manifesto-word',
        { color: 'rgba(234, 231, 224, 0.13)' },
        {
          color: '#eae7e0',
          ease: 'none',
          duration: isCjk ? 0.7 : 1.6,
          stagger: isCjk ? 0.06 : 0.32,
          scrollTrigger: {
            trigger: root,
            start: 'top top',
            end: 'bottom bottom',
            scrub: 0.5,
          },
        },
      )

      // 硬件数量：钉住瞬间数字自动播放一次（时间驱动，不随滚动增减），
      // stagger 形成从左到右的接力滚动
      const counters = STAT_ITEMS.map(() => ({ value: 0 }))
      const counterTl = gsap.timeline({
        scrollTrigger: { trigger: root, start: 'top top+=2', once: true },
      })

      counters.forEach((counter, index) => {
        const target = STAT_ITEMS[index]?.value ?? 0
        counterTl.to(
          counter,
          {
            value: target,
            duration: 1.6,
            ease: 'power2.out',
            onUpdate: () => {
              const element = numberRefs.current[index]
              if (element) {
                element.textContent = String(Math.round(counter.value))
              }
            },
          },
          index * 0.08,
        )
      })

      // 统计行入场：与数字滚动同刻淡入上移
      gsap.from('.wl-stats-row', {
        opacity: 0,
        y: 24,
        duration: 0.6,
        ease: 'power2.out',
        scrollTrigger: { trigger: root, start: 'top top+=2', once: true },
      })
    }, root)

    return () => ctx.revert()
    // 语言切换后文案与切词粒度都会变，需要按新结构重建滚动触发器
  }, [isCjk])

  return (
    // 第二区：文本区（逐词显白）+ 硬件数量区（钉底 + 首次进入自动滚动计数）
    <section id="manifesto" ref={rootRef} className="relative z-10 h-[170svh] bg-[#0a0a0a]">
      {/* 左右内边距与 hero 卡一致：统计行宽度等于首屏红色卡片宽度 */}
      <div className="sticky top-0 flex h-screen flex-col px-3 md:px-10">
        <div className="flex flex-1 items-center justify-center">
          <p className="mx-auto max-w-5xl text-center font-serif text-[clamp(2rem,4.2vw,3.5rem)] leading-[1.18] font-medium">
            {words.map((word, index) => (
              <span
                key={`${word.text}-${index}`}
                className={isCjk ? 'wl-manifesto-word wl-manifesto-word-cjk' : 'wl-manifesto-word'}
                style={word.hasSpaceBefore ? { marginLeft: '0.18em' } : undefined}
              >
                {word.text}
              </span>
            ))}
          </p>
        </div>

        {/* 桌面端 8 列 + 渐变分隔线均分整卡宽度；窄屏换行排布 */}
        <div className="wl-stats-row flex flex-wrap items-start justify-center gap-x-8 gap-y-5 pb-6 md:flex-nowrap md:items-stretch md:justify-between md:gap-x-0 md:pb-10">
          {STAT_ITEMS.map((stat, index) => (
            <Fragment key={stat.key}>
              {index === 0 ? null : (
                <div className="wl-stat-divider hidden md:block" aria-hidden="true" />
              )}
              <div className="flex flex-col items-center gap-2 md:flex-1">
                <span className="text-sm tracking-[0.22em] text-[#eae7e0]/50 uppercase">
                  {t(`welcome.landing.manifesto.stats.${stat.key}`)}
                </span>
                <span
                  ref={(element) => {
                    numberRefs.current[index] = element
                  }}
                  className="text-4xl font-medium text-[#eae7e0] tabular-nums md:text-5xl lg:text-[3.25rem]"
                >
                  {stat.value}
                </span>
              </div>
            </Fragment>
          ))}
        </div>
      </div>
    </section>
  )
}
