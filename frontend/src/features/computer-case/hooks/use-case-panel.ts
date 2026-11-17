import { useCallback, useLayoutEffect, useState, type RefObject } from 'react'

/**
 * 对话容器可用宽度低于该值时自动收起机箱面板：
 * 720px 对话版心 + 左右留白之后，仍要保证右侧 3D 区有可读的构图空间。
 */
export const CASE_PANEL_MIN_CONTAINER_WIDTH = 880

export interface CasePanelState {
  /** 容器是否有足够空间展示机箱 */
  readonly hasRoom: boolean
  /** 用户是否主动隐藏了机箱 */
  readonly isHiddenByUser: boolean
  /** 是否应挂载机箱面板（有空间且未被用户隐藏） */
  readonly shouldRenderCase: boolean
  /** 是否展示恢复入口（有空间但被用户隐藏） */
  readonly canRestoreCase: boolean
  readonly hideCase: () => void
  readonly showCase: () => void
}

/**
 * 机箱面板的可见性控制。
 *
 * 空间判断放在容器级而不是视口级：侧栏可拖拽，视口宽度不能代表对话区真实可用宽度。
 * 用户隐藏是可恢复偏好；空间不足属于临时约束，拖宽后自动恢复展示。
 *
 * @param containerRef - 同时容纳对话与机箱的容器引用，交由调用方绑定到 JSX
 */
export function useCasePanel(containerRef: RefObject<HTMLDivElement | null>): CasePanelState {
  const [containerWidth, setContainerWidth] = useState(0)
  const [isHiddenByUser, setIsHiddenByUser] = useState(false)

  // layout effect 在浏览器绘制前完成首次测量，避免先渲染居中对话、下一帧再跳到左侧
  useLayoutEffect(() => {
    const element = containerRef.current
    if (!element) return
    setContainerWidth(element.clientWidth)
    if (typeof ResizeObserver === 'undefined') return

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) setContainerWidth(entry.contentRect.width)
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [containerRef])

  const hasRoom = containerWidth >= CASE_PANEL_MIN_CONTAINER_WIDTH

  const hideCase = useCallback((): void => setIsHiddenByUser(true), [])
  const showCase = useCallback((): void => setIsHiddenByUser(false), [])

  return {
    hasRoom,
    isHiddenByUser,
    shouldRenderCase: hasRoom && !isHiddenByUser,
    canRestoreCase: hasRoom && isHiddenByUser,
    hideCase,
    showCase,
  }
}
