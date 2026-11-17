import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'

import { createCameraFocus, type CameraFocus } from '../lib/case-camera-focus'
import { createCaseMarkers, type CaseMarker } from '../lib/case-markers'
import { loadCaseModel } from '../lib/case-model'
import { createThreeSetup, type ThreeSetup } from '../lib/case-scene'

export interface CaseNavItem {
  readonly id: string
  readonly label: string
}

export interface ComputerCaseState {
  readonly navItems: readonly CaseNavItem[]
  /** 当前聚焦的组件 id；null 表示全景 */
  readonly activeId: string | null
  readonly isLoading: boolean
  /** 模型下载进度 0~100；null 表示响应未带 Content-Length */
  readonly progress: number | null
  readonly hasError: boolean
  readonly select: (id: string) => void
  readonly retry: () => void
}

/**
 * 机箱 3D 组件编排。
 *
 * 场景生命周期与 React 解耦：effect 只负责创建/销毁，rAF 循环与模型状态留在普通对象里。
 * 首次创建延迟一帧，避开 StrictMode 开发期「挂载→卸载→再挂载」导致的两套 WebGL 上下文
 * 与重复的模型下载。
 *
 * @param containerRef - 承载 renderer canvas 的容器引用，交由调用方绑定到 JSX
 */
export function useComputerCase(containerRef: RefObject<HTMLDivElement | null>): ComputerCaseState {
  const [navItems, setNavItems] = useState<readonly CaseNavItem[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [progress, setProgress] = useState<number | null>(null)
  const [hasError, setHasError] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)

  const markersRef = useRef<readonly CaseMarker[]>([])
  const focusRef = useRef<CameraFocus | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    let cancelled = false
    let frameId = 0
    let setup: ThreeSetup | null = null

    setNavItems([])
    setActiveId(null)
    setIsLoading(true)
    setProgress(null)
    setHasError(false)

    frameId = window.requestAnimationFrame(() => {
      if (cancelled) return
      try {
        setup = createThreeSetup(container)
      } catch (error) {
        // WebGL 不可用（老显卡/被禁用）时降级为错误态，不阻塞对话
        console.error('机箱 3D 场景初始化失败', error)
        setIsLoading(false)
        setHasError(true)
        return
      }

      loadCaseModel(setup, (percent) => {
        if (!cancelled) setProgress(percent)
      })
        .then((model) => {
          if (cancelled || !setup || setup.isDisposed) return
          const markers = createCaseMarkers(model)
          markersRef.current = markers
          focusRef.current = createCameraFocus(setup, model.root, model.maxDim)
          setNavItems(markers.map((marker) => ({ id: marker.config.id, label: marker.config.label })))
        })
        .catch(() => {
          if (!cancelled) setHasError(true)
        })
        .finally(() => {
          if (!cancelled) setIsLoading(false)
        })
    })

    return () => {
      cancelled = true
      window.cancelAnimationFrame(frameId)
      setup?.dispose()
      markersRef.current = []
      focusRef.current = null
    }
  }, [containerRef, reloadToken])

  const select = useCallback(
    (id: string): void => {
      const marker = markersRef.current.find((item) => item.config.id === id)
      const focus = focusRef.current
      if (!marker || !focus) return

      // 再次点击同一项取消聚焦并复位全景
      if (activeId === id) {
        setActiveId(null)
        focus.resetView()
        return
      }
      setActiveId(id)
      // 传锚点对象而非坐标：聚焦需借助锚点挂载的目标网格做射线可见性判断，挑不被遮挡的方位
      focus.focusOn(marker.anchor)
    },
    [activeId],
  )

  const retry = useCallback((): void => {
    setReloadToken((token) => token + 1)
  }, [])

  return { navItems, activeId, isLoading, progress, hasError, select, retry }
}
