import { useEffect, useId, useState } from 'react'

import { formatFen } from '@/shared/lib/format'
import { cn } from '@/shared/lib/utils'

/** 偏好减动效时直接落到终值，避免入场动画成为干扰 */
const prefersReducedMotion = (): boolean =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

/**
 * 0 → target 的缓动计数：只用于图表读数，收尾用 easeOutCubic。
 * 不依赖任何图表库，减少首屏 JS 体积；偏好减动效时直接返回目标值。
 */
function useCountUp(target: number, durationMs = 900): number {
  const [value, setValue] = useState(0)

  useEffect(() => {
    if (prefersReducedMotion() || typeof requestAnimationFrame !== 'function') {
      return
    }

    let frame = 0
    const startedAt = performance.now()
    const step = (now: number): void => {
      const progress = Math.min(1, (now - startedAt) / durationMs)
      setValue(target * (1 - (1 - progress) ** 3))
      if (progress < 1) {
        frame = requestAnimationFrame(step)
      }
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [target, durationMs])

  if (prefersReducedMotion() || typeof requestAnimationFrame !== 'function') {
    return target
  }
  return value
}

/** 环形渐变 id：useId 自带冒号，直接拼进 url(#…) 会失效 */
function useSvgId(prefix: string): string {
  return `${prefix}-${useId().replace(/:/g, '')}`
}

/** 以 0° 指向上方的极坐标取点，供各图表复用 */
const polarPoint = (cx: number, cy: number, angleDeg: number, radius: number): [number, number] => {
  const rad = ((angleDeg - 90) * Math.PI) / 180
  return [cx + Math.cos(rad) * radius, cy + Math.sin(rad) * radius]
}

/** 拼一条圆弧路径，角度按「12 点方向为 0°、顺时针递增」计算 */
const describeArc = (
  cx: number,
  cy: number,
  radius: number,
  startDeg: number,
  sweepDeg: number,
): string => {
  const [startX, startY] = polarPoint(cx, cy, startDeg, radius)
  const [endX, endY] = polarPoint(cx, cy, startDeg + sweepDeg, radius)
  const largeArc = sweepDeg > 180 ? 1 : 0
  return `M ${startX.toFixed(2)} ${startY.toFixed(2)} A ${radius} ${radius} 0 ${largeArc} 1 ${endX.toFixed(2)} ${endY.toFixed(2)}`
}

/* ------------------------------------------------------------------ */
/* 预算分配：横向条形图                                                 */
/* ------------------------------------------------------------------ */

export interface BudgetSliceView {
  readonly key: string
  readonly label: string
  readonly amountFen: number
  readonly ratio: number
}

/**
 * 预算分配条形图（对照参考实现 BarChart.vue）。
 *
 * 一行 = 类目名 + 灰底轨道 + 渐变条 + 行尾占比，条与文字同一行；
 * 条高取行高的 60%，随卡片高度自适应加粗，而不是固定像素细线。
 */
export function BudgetAllocationChart({ items }: { readonly items: readonly BudgetSliceView[] }) {
  // 减动效时首帧即终态，避免条形从 0 跳到目标
  const [isGrown, setIsGrown] = useState(prefersReducedMotion)

  useEffect(() => {
    if (prefersReducedMotion() || typeof requestAnimationFrame !== 'function') {
      return
    }
    const frame = requestAnimationFrame(() => setIsGrown(true))
    return () => cancelAnimationFrame(frame)
  }, [])

  if (items.length === 0) {
    return <p className="text-xs text-muted-foreground">—</p>
  }

  const sorted = [...items].sort((left, right) => right.ratio - left.ratio)

  return (
    <ul className="flex h-full min-h-0 flex-col justify-between gap-1">
      {sorted.map((item) => (
        <li key={item.key} className="flex min-w-0 shrink-0 items-center gap-2">
          <span className="w-10 shrink-0 truncate text-[12px] leading-tight text-muted-foreground">
            {item.label}
          </span>
          {/* 轨道与条形同一圆角：底槽给出「满格」参照，条形只表达占比 */}
          <span className="relative h-2 min-w-0 flex-1 overflow-hidden rounded-md bg-muted/40">
            <span
              className="absolute inset-y-0 left-0 rounded-md transition-[width] duration-700 ease-out"
              style={{
                width: isGrown ? `${Math.min(100, item.ratio)}%` : '0%',
                background:
                  'linear-gradient(90deg, var(--cds-orange-600), var(--cds-clay) 60%, var(--cds-orange-400))',
              }}
            />
          </span>
          <span className="w-10 shrink-0 text-right text-[12px] leading-tight tabular-nums text-muted-foreground">
            {item.ratio.toFixed(1)}%
          </span>
        </li>
      ))}
    </ul>
  )
}

/* ------------------------------------------------------------------ */
/* 预算结构雷达图                                                       */
/* ------------------------------------------------------------------ */

const RADAR_SIZE = 220
const RADAR_CENTER = RADAR_SIZE / 2
const RADAR_RADIUS = 74
const RADAR_LABEL_RADIUS = 92
const RADAR_LEVELS = 4

const toPoint = (angleDeg: number, radius: number): [number, number] => {
  const rad = ((angleDeg - 90) * Math.PI) / 180
  return [RADAR_CENTER + Math.cos(rad) * radius, RADAR_CENTER + Math.sin(rad) * radius]
}

const polygonPoints = (values: readonly number[], max: number): string =>
  values
    .map((value, index) => {
      const angle = (360 / values.length) * index
      const radius = max <= 0 ? 0 : (Math.min(max, Math.max(0, value)) / max) * RADAR_RADIUS
      return toPoint(angle, radius).join(',')
    })
    .join(' ')

export interface RadarAxis {
  readonly key: string
  readonly label: string
  /** 真实占比（0-100），标签直接展示该值 */
  readonly value: number
}

/**
 * 预算结构雷达：轴为硬件品类，值为该品类占总价比例。
 *
 * 视觉对照参考实现 RadarChart.vue：交替底色环带（splitArea）、
 * 轴线/网格弱化、数据面用径向渐隐 + 描边，轴标签同时给出数值避免误读。
 */
export function BudgetRadarChart({ axes }: { readonly axes: readonly RadarAxis[] }) {
  const gradientId = useSvgId('build-radar')
  const maxValue = Math.max(10, ...axes.map((axis) => axis.value))
  const scaleMax = Math.min(100, Math.ceil(maxValue / 10) * 10)
  const points = polygonPoints(
    axes.map((axis) => axis.value),
    scaleMax,
  )
  const description = axes.map((axis) => `${axis.label} ${axis.value.toFixed(1)}%`).join('，')

  if (axes.length < 3) {
    return <p className="text-xs text-muted-foreground">—</p>
  }

  return (
    <figure
      className="flex h-full min-h-0 w-full flex-col items-center justify-center"
      role="img"
      aria-label={description}
      title={description}
    >
      <svg
        viewBox={`0 0 ${RADAR_SIZE} ${RADAR_SIZE}`}
        className="h-full w-full"
        preserveAspectRatio="xMidYMid meet"
        aria-hidden="true"
      >
        <defs>
          <radialGradient id={gradientId} cx="50%" cy="50%" r="70%">
            <stop offset="0%" stopColor="var(--cds-clay)" stopOpacity="0.38" />
            <stop offset="100%" stopColor="var(--cds-clay)" stopOpacity="0.08" />
          </radialGradient>
        </defs>

        {/* 交替底色环带：由外向内一层层收窄，给盘面体积感 */}
        {Array.from({ length: RADAR_LEVELS }, (_, levelIndex) => {
          const outerRadius = (RADAR_RADIUS / RADAR_LEVELS) * (RADAR_LEVELS - levelIndex)
          const innerRadius =
            levelIndex === RADAR_LEVELS - 1
              ? 0
              : (RADAR_RADIUS / RADAR_LEVELS) * (RADAR_LEVELS - levelIndex - 1)
          const outerPoints = axes
            .map((_, index) => toPoint((360 / axes.length) * index, outerRadius).join(','))
            .join(' ')
          const innerPoints = axes
            .map((_, index) => toPoint((360 / axes.length) * index, innerRadius).join(','))
            .join(' ')
          return (
            <polygon
              key={levelIndex}
              points={`${outerPoints} ${innerPoints}`}
              fill="var(--cds-clay)"
              fillOpacity={levelIndex % 2 === 0 ? 0.05 : 0.015}
              stroke="var(--cds-border)"
              strokeWidth={0.6}
            />
          )
        })}

        {/* 轴线 */}
        {axes.map((axis, index) => {
          const [x, y] = toPoint((360 / axes.length) * index, RADAR_RADIUS)
          return (
            <line
              key={axis.key}
              x1={RADAR_CENTER}
              y1={RADAR_CENTER}
              x2={x}
              y2={y}
              stroke="var(--cds-border)"
              strokeWidth={0.6}
            />
          )
        })}

        <polygon
          points={points}
          fill={`url(#${gradientId})`}
          stroke="var(--cds-clay)"
          strokeWidth={1.8}
          strokeLinejoin="round"
        />

        {axes.map((axis, index) => {
          const angle = (360 / axes.length) * index
          const ratio = scaleMax <= 0 ? 0 : Math.min(1, Math.max(0, axis.value / scaleMax))
          const [cx, cy] = toPoint(angle, ratio * RADAR_RADIUS)
          return <circle key={axis.key} cx={cx} cy={cy} r={2.2} fill="var(--cds-clay)" />
        })}

        {/* 轴名 + 真实占比：标签放在多边形外侧，按方位调整对齐 */}
        {axes.map((axis, index) => {
          const angle = (360 / axes.length) * index
          const [x, y] = toPoint(angle, RADAR_LABEL_RADIUS)
          const isRight = x > RADAR_CENTER + 4
          const isLeft = x < RADAR_CENTER - 4
          return (
            <text
              key={axis.key}
              x={x}
              y={y}
              textAnchor={isRight ? 'start' : isLeft ? 'end' : 'middle'}
              dominantBaseline="middle"
              fontSize={9.5}
              fill="var(--muted-foreground)"
            >
              <tspan>{axis.label}</tspan>
              <tspan x={x} dy="10.5" fontSize={9} fill="var(--foreground)">
                {axis.value.toFixed(1)}%
              </tspan>
            </text>
          )
        })}
      </svg>
    </figure>
  )
}

/* ------------------------------------------------------------------ */
/* 仪表盘：按参考实现的 420×420 设计稿逐层移植                           */
/* ------------------------------------------------------------------ */

/**
 * 设计稿尺寸：参考实现固定 420×420 渲染再整体 scale，
 * 这里用等价做法——viewBox 420、外层 h-full w-full + preserveAspectRatio，
 * 所有半径/线宽都按设计稿像素写死，容器缩放时整盘等比缩放不变形。
 */
const GAUGE_SIZE = 420
const GAUGE_CENTER = GAUGE_SIZE / 2
/** 量程：225° 起步、顺时针 270°，缺口朝下（与 ECharts 默认一致） */
const GAUGE_START_DEG = 225
const GAUGE_SWEEP_DEG = 270
/** 刻度环半径 65% */
const GAUGE_TICK_RADIUS = 136.5
/** 进度弧半径 73%、线宽 19 */
const GAUGE_ARC_RADIUS = 153.3
const GAUGE_ARC_WIDTH = 19
/** 最外层高亮细弧半径 80%、线宽 6 */
const GAUGE_OUTER_RADIUS = 168
const GAUGE_OUTER_WIDTH = 6
/** 指针长度 80% */
const GAUGE_POINTER_LENGTH = 122.6
/** 中心暗盘与内环（对应参考实现的 pie 0-20% / 20-25%） */
const GAUGE_DISC_RADIUS = 42
const GAUGE_RING_RADIUS = 52.5

export interface BuildGaugeProps {
  /** 弧线比例（0-100），已按类目参考上限归一化 */
  readonly value: number
  /** 中心展示的真实读数（跑分 / 百分比） */
  readonly displayValue: string
  readonly label: string
  /** 悬停说明：解释弧线比例口径，避免读数被误解 */
  readonly hint?: string
}

/**
 * 表盘式仪表盘：逐层复刻参考实现 Dashboard.vue 的五个 series——
 * ① 65% 半径刻度环 ② 73% 暗色轨道 ③ 73% 渐变进度弧 + 指针
 * ④ 80% 外侧渐隐高亮弧 ⑤ 中心暗盘与细环，另加大号读数与说明文字。
 */
export function BuildGauge({ value, displayValue, label, hint }: BuildGaugeProps) {
  const gradientId = useSvgId('build-gauge-progress')
  const outerId = useSvgId('build-gauge-outer')
  const discId = useSvgId('build-gauge-disc')
  const clamped = Math.max(0, Math.min(100, value))
  const sweep = (clamped / 100) * GAUGE_SWEEP_DEG
  const needleAngle = GAUGE_START_DEG + sweep
  // 读数过长（如 174,825）时降字号，避免溢出中心暗盘
  const valueFontSize = displayValue.length > 6 ? 34 : 44

  return (
    <figure
      className="flex h-full w-full items-center justify-center"
      role="img"
      aria-label={`${label} ${displayValue}`}
      title={hint ?? label}
    >
      <svg
        viewBox={`0 0 ${GAUGE_SIZE} ${GAUGE_SIZE}`}
        className="h-full w-full"
        preserveAspectRatio="xMidYMid meet"
        aria-hidden="true"
      >
        <defs>
          {/* 进度弧：纵向深→浅，与参考实现同向；末端不用最浅档，避免浅色主题下发白 */}
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--cds-orange-600)" />
            <stop offset="55%" stopColor="var(--cds-clay)" />
            <stop offset="100%" stopColor="var(--cds-orange-400)" />
          </linearGradient>
          {/* 外侧高亮弧：从深色收尾到透明 */}
          <linearGradient id={outerId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--cds-orange-600)" stopOpacity="0.95" />
            <stop offset="100%" stopColor="var(--cds-orange-600)" stopOpacity="0" />
          </linearGradient>
          <radialGradient id={discId} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--cds-clay)" stopOpacity="0.14" />
            <stop offset="70%" stopColor="var(--cds-clay)" stopOpacity="0.04" />
            <stop offset="100%" stopColor="var(--cds-clay)" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* ① 刻度环：10 大格、每格 4 小格，长短交替 */}
        <g aria-hidden="true">
          {Array.from({ length: 41 }, (_, index) => {
            const angle = GAUGE_START_DEG + (GAUGE_SWEEP_DEG / 40) * index
            const isMajor = index % 4 === 0
            const outerPoint = polarPoint(
              GAUGE_CENTER,
              GAUGE_CENTER,
              angle,
              GAUGE_TICK_RADIUS,
            )
            const innerPoint = polarPoint(
              GAUGE_CENTER,
              GAUGE_CENTER,
              angle,
              GAUGE_TICK_RADIUS - (isMajor ? 10 : 5),
            )
            return (
              <line
                key={index}
                x1={outerPoint[0]}
                y1={outerPoint[1]}
                x2={innerPoint[0]}
                y2={innerPoint[1]}
                stroke="var(--muted-foreground)"
                strokeOpacity={isMajor ? 0.7 : 0.38}
                strokeWidth={isMajor ? 1.4 : 0.8}
                strokeLinecap="round"
              />
            )
          })}
        </g>

        {/* ② 暗色轨道：整段 270°，仅作参照 */}
        <path
          d={describeArc(
            GAUGE_CENTER,
            GAUGE_CENTER,
            GAUGE_ARC_RADIUS,
            GAUGE_START_DEG,
            GAUGE_SWEEP_DEG,
          )}
          fill="none"
          stroke="var(--cds-clay)"
          strokeOpacity="0.3"
          strokeWidth={GAUGE_ARC_WIDTH}
        />

        {/* ④ 外侧高亮弧：比进度弧更细、更靠外，形成双层描边 */}
        {clamped > 0 ? (
          <path
            d={describeArc(
              GAUGE_CENTER,
              GAUGE_CENTER,
              GAUGE_OUTER_RADIUS,
              GAUGE_START_DEG,
              sweep,
            )}
            fill="none"
            stroke={`url(#${outerId})`}
            strokeWidth={GAUGE_OUTER_WIDTH}
            strokeLinecap="round"
          />
        ) : null}

        {/* ③ 进度弧 */}
        {clamped > 0 ? (
          <path
            d={describeArc(
              GAUGE_CENTER,
              GAUGE_CENTER,
              GAUGE_ARC_RADIUS,
              GAUGE_START_DEG,
              sweep,
            )}
            fill="none"
            stroke={`url(#${gradientId})`}
            strokeWidth={GAUGE_ARC_WIDTH}
          />
        ) : null}

        {/* 中心暗盘 + 细环：衬托读数，避免数字直接压在背景上 */}
        <circle cx={GAUGE_CENTER} cy={GAUGE_CENTER} r={GAUGE_DISC_RADIUS} fill="var(--cds-clay)" fillOpacity="0.06" />
        <circle cx={GAUGE_CENTER} cy={GAUGE_CENTER} r={GAUGE_DISC_RADIUS} fill={`url(#${discId})`} />
        <circle
          cx={GAUGE_CENTER}
          cy={GAUGE_CENTER}
          r={GAUGE_RING_RADIUS}
          fill="none"
          stroke="var(--cds-clay)"
          strokeOpacity="0.18"
          strokeWidth={10}
        />

        {/* 指针：从圆心指向当前值，无轴心点（与参考实现 anchor.show=false 一致） */}
        <g transform={`rotate(${needleAngle} ${GAUGE_CENTER} ${GAUGE_CENTER})`}>
          <path
            d={`M ${GAUGE_CENTER - 5} ${GAUGE_CENTER} L ${GAUGE_CENTER} ${GAUGE_CENTER - GAUGE_POINTER_LENGTH} L ${GAUGE_CENTER + 5} ${GAUGE_CENTER} Z`}
            fill="var(--cds-clay)"
          />
        </g>

        {/* 读数与说明：跟随 viewBox 等比缩放 */}
        <text
          x={GAUGE_CENTER}
          y={GAUGE_CENTER + 24}
          textAnchor="middle"
          fontSize={valueFontSize}
          fontWeight="bold"
          fill="var(--foreground)"
          style={{ fontVariantNumeric: 'tabular-nums' }}
        >
          {displayValue}
        </text>
        <text
          x={GAUGE_CENTER}
          y={GAUGE_CENTER + 0.86 * GAUGE_ARC_RADIUS + 10}
          textAnchor="middle"
          fontSize="30"
          fontWeight="500"
          fill="var(--muted-foreground)"
        >
          {label}
        </text>
      </svg>
    </figure>
  )
}

/* ------------------------------------------------------------------ */
/* 预算用量水波图                                                       */
/* ------------------------------------------------------------------ */

export interface BudgetWaterWaveProps {
  /** 总价占预算比例；超预算时大于 100 */
  readonly ratio: number
  readonly totalFen: number
  readonly budgetFen: number
  readonly title: string
  readonly budgetLabel: string
  readonly currentLabel: string
  readonly overLabel: string
  readonly remainingLabel: string
}

/** 生成一段可平铺的正弦水面：振幅 5，波长 40，横向多铺几段保证无缝滚动 */
const buildWavePath = (surfaceY: number, offsetX: number): string => {
  const segments = 12
  let path = `M ${-80 + offsetX} ${surfaceY}`
  for (let index = 0; index < segments; index += 1) {
    path += ' q 10 -5 20 0 t 20 0'
  }
  return `${path} L 240 ${160} L -80 ${160} Z`
}

/**
 * 预算用量水波图（对照参考实现 WaterWaveDiagram.vue 的排版）：
 * 左列为占比说明与金额明细，右列为水波盘，横排而不是上下堆叠。
 *
 * 水位 = 总价占预算比例；超预算时切换警示色并显示超出金额。
 */
export function BudgetWaterWave({
  ratio,
  totalFen,
  budgetFen,
  title,
  budgetLabel,
  currentLabel,
  overLabel,
  remainingLabel,
}: BudgetWaterWaveProps) {
  const gradientId = useSvgId('build-water')
  const clipId = useSvgId('build-water-clip')
  const animated = useCountUp(Math.max(0, Math.min(100, ratio)))
  const isOver = ratio > 100
  const overFen = Math.max(0, totalFen - budgetFen)
  const remainingFen = Math.max(0, budgetFen - totalFen)
  const level = Math.max(0, Math.min(100, animated))
  const surfaceY = 138 - 1.16 * level
  const shouldAnimate = !prefersReducedMotion()

  return (
    <figure
      className="flex h-full min-h-0 w-full items-center justify-center gap-2.5"
      role="img"
      aria-label={`${title} ${Math.round(ratio)}%`}
    >
      {/* 左列：说明 + 金额明细，溢出时追加红字 */}
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="whitespace-nowrap text-[12px] text-foreground/70">{title}</span>
        <span className="flex items-baseline justify-between gap-2 whitespace-nowrap text-[12px] text-muted-foreground">
          <span>{budgetLabel}</span>
          <span className="tabular-nums">{formatFen(budgetFen)}</span>
        </span>
        <span className="flex items-baseline justify-between gap-2 whitespace-nowrap text-[12px] text-muted-foreground">
          <span>{currentLabel}</span>
          <span className="tabular-nums">{formatFen(totalFen)}</span>
        </span>
        <span
          className={cn(
            'flex items-baseline justify-between gap-2 whitespace-nowrap text-[12px] font-medium',
            isOver ? 'text-destructive' : 'text-success',
          )}
        >
          <span>{isOver ? overLabel : remainingLabel}</span>
          <span className="tabular-nums">{formatFen(isOver ? overFen : remainingFen)}</span>
        </span>
      </div>

      {/* 右列：正方形水波盘，宽高都吃满可用空间 */}
      <div className="relative aspect-square h-full max-h-[142px] min-h-0 shrink-0">
        <svg
          viewBox="0 0 160 160"
          className="h-full w-full"
          preserveAspectRatio="xMidYMid meet"
          aria-hidden="true"
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--cds-orange-400)" stopOpacity="0.9" />
              <stop offset="100%" stopColor="var(--cds-orange-600)" stopOpacity="0.95" />
            </linearGradient>
            <clipPath id={clipId}>
              <circle cx="80" cy="80" r="56" />
            </clipPath>
          </defs>

          {/* 外圈刻度：只作仪表感装饰，不承载数据 */}
          <g aria-hidden="true">
            {Array.from({ length: 48 }, (_, index) => {
              const angle = (360 / 48) * index
              const isMajor = index % 4 === 0
              const outerPoint = polarPoint(80, 80, angle, 68)
              const innerPoint = polarPoint(80, 80, angle, isMajor ? 62 : 65)
              return (
                <line
                  key={index}
                  x1={outerPoint[0]}
                  y1={outerPoint[1]}
                  x2={innerPoint[0]}
                  y2={innerPoint[1]}
                  stroke="var(--muted-foreground)"
                  strokeOpacity={isMajor ? 0.45 : 0.25}
                  strokeWidth={isMajor ? 1.2 : 0.7}
                  strokeLinecap="round"
                />
              )
            })}
          </g>

          <circle cx="80" cy="80" r="56" fill="var(--cds-surface-2)" />

          <g clipPath={`url(#${clipId})`}>
            <rect
              x="0"
              y={surfaceY}
              width="160"
              height={Math.max(0, 160 - surfaceY)}
              fill={`url(#${gradientId})`}
            />
            {/* 第一层水面：慢速；第二层更透明，形成前后错位的波动 */}
            <path d={buildWavePath(surfaceY, 0)} fill={`url(#${gradientId})`} fillOpacity="0.6">
              {shouldAnimate ? (
                <animateTransform
                  attributeName="transform"
                  type="translate"
                  from="0 0"
                  to="-80 0"
                  dur="6s"
                  repeatCount="indefinite"
                />
              ) : null}
            </path>
            <path
              d={buildWavePath(surfaceY + 3, 24)}
              fill={`url(#${gradientId})`}
              fillOpacity="0.35"
            >
              {shouldAnimate ? (
                <animateTransform
                  attributeName="transform"
                  type="translate"
                  from="0 0"
                  to="-80 0"
                  dur="9s"
                  repeatCount="indefinite"
                />
              ) : null}
            </path>
          </g>

          <circle
            cx="80"
            cy="80"
            r="56"
            fill="none"
            stroke={isOver ? 'var(--destructive)' : 'var(--cds-clay)'}
            strokeWidth="2.5"
            strokeOpacity="0.55"
          />

          {/* 读数：描边+填充保证任何水位下都可读 */}
          <text
            x="80"
            y="86"
            textAnchor="middle"
            fontSize="26"
            fontWeight="600"
            fill="var(--foreground)"
            stroke="var(--cds-surface-2)"
            strokeWidth="3"
            paintOrder="stroke"
            style={{ fontVariantNumeric: 'tabular-nums' }}
          >
            {Math.round(ratio)}%
          </text>
        </svg>
      </div>
    </figure>
  )
}

/* ------------------------------------------------------------------ */
/* 底部半圆表                                                           */
/* ------------------------------------------------------------------ */

export interface ScoreSemicircleProps {
  /** 0-100 的真实比例 */
  readonly value: number
  readonly displayValue: string
  readonly title: string
  readonly subtitle: string
  readonly hint?: string
}

/** 设计稿：弦长贴左右、矢高占容器高 80%，与参考实现的自适应浅弧同一套几何 */
const SEMI_WIDTH = 700
const SEMI_HEIGHT = 200
const SEMI_PAD_X = 6
/** 弦线抬高 6px，给两端圆头留出空间，避免被容器下沿裁切 */
const SEMI_BASELINE = SEMI_HEIGHT - 6
const SEMI_SAGITTA = SEMI_BASELINE * 0.8
const SEMI_CHORD = SEMI_WIDTH - SEMI_PAD_X * 2
const SEMI_RADIUS = (SEMI_CHORD * SEMI_CHORD) / (8 * SEMI_SAGITTA) + SEMI_SAGITTA / 2

/**
 * 底部主半圆表：巨圆露出浅弧，弦长按宽度撑满、矢高按高度 80% 反推半径，
 * 因此任何宽高比都铺满容器；弧长表达 0-100 的真实比例。
 */
export function ScoreSemicircle({
  value,
  displayValue,
  title,
  subtitle,
  hint,
}: ScoreSemicircleProps) {
  const gradientId = useSvgId('build-score-arc')
  const dimId = useSvgId('build-score-dim')
  const animated = useCountUp(Math.max(0, Math.min(100, value)))

  const arcPath = `M ${SEMI_PAD_X} ${SEMI_BASELINE} A ${SEMI_RADIUS} ${SEMI_RADIUS} 0 0 1 ${SEMI_WIDTH - SEMI_PAD_X} ${SEMI_BASELINE}`

  return (
    <figure
      className="flex h-full w-full items-center justify-center"
      role="img"
      aria-label={`${title} ${displayValue}`}
      title={hint ?? subtitle}
    >
      <svg
        viewBox={`0 0 ${SEMI_WIDTH} ${SEMI_HEIGHT}`}
        className="h-full w-full"
        preserveAspectRatio="xMidYMid meet"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--cds-orange-600)" stopOpacity="0.4" />
            <stop offset="30%" stopColor="var(--cds-orange-600)" />
            <stop offset="50%" stopColor="var(--cds-clay)" />
            <stop offset="70%" stopColor="var(--cds-orange-600)" />
            <stop offset="100%" stopColor="var(--cds-orange-600)" stopOpacity="0.4" />
          </linearGradient>
          <linearGradient id={dimId} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--cds-border)" stopOpacity="0.25" />
            <stop offset="50%" stopColor="var(--cds-border)" stopOpacity="0.9" />
            <stop offset="100%" stopColor="var(--cds-border)" stopOpacity="0.25" />
          </linearGradient>
        </defs>

        {/* 暗弧铺底 */}
        <path
          d={arcPath}
          fill="none"
          stroke={`url(#${dimId})`}
          strokeWidth="6"
          strokeLinecap="round"
        />
        {/* 进度亮弧：pathLength 归一化后直接用 dasharray 表达比例 */}
        <path
          d={arcPath}
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth="6"
          strokeLinecap="round"
          pathLength={100}
          strokeDasharray={`${(animated / 100) * 100} 100`}
        />

        {/* 内侧细边弧：与主弧平行，补一层纵深 */}
        <path
          d={arcPath}
          fill="none"
          stroke="var(--cds-clay)"
          strokeOpacity="0.35"
          strokeWidth="1"
          transform={`translate(0 10)`}
        />

        {/* 读数与说明：写在 viewBox 内，随容器等比缩放 */}
        <text
          x={SEMI_WIDTH / 2}
          y={SEMI_HEIGHT - 62}
          textAnchor="middle"
          fontSize="48"
          fontWeight="300"
          fill="var(--foreground)"
          style={{ fontVariantNumeric: 'tabular-nums' }}
        >
          {displayValue}
        </text>
        <line
          x1={SEMI_WIDTH / 2 - 132}
          y1={SEMI_HEIGHT - 44}
          x2={SEMI_WIDTH / 2 - 26}
          y2={SEMI_HEIGHT - 44}
          stroke="var(--cds-clay)"
          strokeOpacity="0.45"
          strokeWidth="1"
        />
        <text
          x={SEMI_WIDTH / 2}
          y={SEMI_HEIGHT - 39}
          textAnchor="middle"
          fontSize="16"
          fill="var(--muted-foreground)"
          letterSpacing="1.5"
        >
          {title}
        </text>
        <line
          x1={SEMI_WIDTH / 2 + 26}
          y1={SEMI_HEIGHT - 44}
          x2={SEMI_WIDTH / 2 + 132}
          y2={SEMI_HEIGHT - 44}
          stroke="var(--cds-clay)"
          strokeOpacity="0.45"
          strokeWidth="1"
        />
        <text
          x={SEMI_WIDTH / 2}
          y={SEMI_HEIGHT - 22}
          textAnchor="middle"
          fontSize="13"
          fill="var(--muted-foreground)"
        >
          {subtitle}
        </text>
      </svg>
    </figure>
  )
}
