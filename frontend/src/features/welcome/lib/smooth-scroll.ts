import Lenis from 'lenis'
import 'lenis/dist/lenis.css'

import { gsap, ScrollTrigger } from './gsap'

/**
 * 欢迎页专用的平滑滚动。
 *
 * 只在落地页启用的原因：阻尼滚动会接管 wheel 事件，工作区（对话、设置）需要
 * 原生滚动的精确定位与滚动容器嵌套；离开落地页必须销毁，恢复原生滚动。
 */
let lenis: Lenis | null = null
let tickerCallback: ((time: number) => void) | null = null

/** 供拆卡区等组件取用：没有实例（减少动效偏好）时调用方回退原生滚动 */
export const getLenis = (): Lenis | null => lenis

export const initSmoothScroll = (): void => {
  if (lenis) {
    return
  }

  // 减少动效偏好下不接管滚动，保证页面仍是可预期的原生滚动
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    return
  }

  const instance = new Lenis({
    duration: 1.05,
    // 站内锚点（导航栏跳转）交给 Lenis 处理，避免原生跳转与阻尼滚动互相拉扯
    anchors: true,
  })

  // 用 GSAP ticker 驱动 raf：滚动与 ScrollTrigger 在同一帧更新，触发点不会抖动
  tickerCallback = (time: number) => instance.raf(time * 1000)
  gsap.ticker.add(tickerCallback)
  gsap.ticker.lagSmoothing(0)

  // 必须包一层：Lenis 会把实例作为参数传出，直接透传会被 ScrollTrigger 当成 force 刷新
  instance.on('scroll', () => ScrollTrigger.update())

  lenis = instance

  // Lenis 会给 html 加上 lenis 类并改写高度计算，滚动容器尺寸随之变化，
  // 需要让已创建的 ScrollTrigger 重新测量一次触发位置
  ScrollTrigger.refresh()
}

export const destroySmoothScroll = (): void => {
  if (tickerCallback) {
    gsap.ticker.remove(tickerCallback)
    tickerCallback = null
  }

  lenis?.destroy()
  lenis = null
}
