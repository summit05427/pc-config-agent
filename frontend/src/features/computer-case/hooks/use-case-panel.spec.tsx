import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { RefObject } from 'react'

import { CASE_PANEL_MIN_CONTAINER_WIDTH, useCasePanel } from './use-case-panel'

/** 捕获 ResizeObserver 回调，便于在测试里手动模拟容器宽度变化 */
let resizeCallback: ResizeObserverCallback | null = null

class ResizeObserverMock {
  constructor(callback: ResizeObserverCallback) {
    resizeCallback = callback
  }
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {
    resizeCallback = null
  }
}

/** 构造一个可指定宽度、无需挂载到文档的容器引用 */
function createContainerRef(width: number): RefObject<HTMLDivElement | null> {
  const container = document.createElement('div')
  Object.defineProperty(container, 'clientWidth', { configurable: true, value: width })
  return { current: container }
}

function emitWidth(width: number): void {
  act(() => {
    resizeCallback?.(
      [{ contentRect: { width } } as ResizeObserverEntry],
      {} as ResizeObserver,
    )
  })
}

describe('useCasePanel', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    resizeCallback = null
  })

  it('容器足够宽时展示机箱，变窄后自动收起并在变宽后恢复', () => {
    vi.stubGlobal('ResizeObserver', ResizeObserverMock)
    // ref 必须在渲染外创建：每次渲染新建 ref 会触发 effect 重跑并把宽度重置成初始值
    const containerRef = createContainerRef(1200)
    const { result } = renderHook(() => useCasePanel(containerRef))

    expect(result.current.hasRoom).toBe(true)
    expect(result.current.shouldRenderCase).toBe(true)

    emitWidth(CASE_PANEL_MIN_CONTAINER_WIDTH - 1)
    expect(result.current.hasRoom).toBe(false)
    expect(result.current.shouldRenderCase).toBe(false)

    emitWidth(CASE_PANEL_MIN_CONTAINER_WIDTH)
    expect(result.current.shouldRenderCase).toBe(true)
  })

  it('用户隐藏后保留恢复入口，恢复后重新展示', () => {
    vi.stubGlobal('ResizeObserver', ResizeObserverMock)
    const containerRef = createContainerRef(1200)
    const { result } = renderHook(() => useCasePanel(containerRef))

    act(() => result.current.hideCase())
    expect(result.current.shouldRenderCase).toBe(false)
    expect(result.current.canRestoreCase).toBe(true)

    act(() => result.current.showCase())
    expect(result.current.shouldRenderCase).toBe(true)
    expect(result.current.canRestoreCase).toBe(false)
  })

  it('容器过窄时不提供恢复入口，避免挤压对话', () => {
    vi.stubGlobal('ResizeObserver', ResizeObserverMock)
    const containerRef = createContainerRef(600)
    const { result } = renderHook(() => useCasePanel(containerRef))

    act(() => result.current.hideCase())
    expect(result.current.canRestoreCase).toBe(false)
  })
})
