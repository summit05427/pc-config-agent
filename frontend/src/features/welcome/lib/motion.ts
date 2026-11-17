/** 用户是否偏好减少动效：命中时所有 GSAP 动效直接呈现终态，只保留静态排版 */
export const prefersReducedMotion = (): boolean =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
