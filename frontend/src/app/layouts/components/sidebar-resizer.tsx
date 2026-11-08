import { useEffect, useRef, useState } from 'react'

import { cn } from '@/shared/lib/utils'

import { SIDEBAR_LAYOUT } from '../lib/sidebar'

type FinishMode = 'commit' | 'cancel'

export interface SidebarResizerProps {
    /** 父级已提交的展开宽度 */
    width: number
    /** 视口允许的最大宽度 */
    max: number
    /** 折叠态下这条边界改为「点击展开」入口 */
    collapsed: boolean
    label: string
    expandLabel: string
    onStart: () => void
    onResize: (width: number) => void
    onCommit: (width: number) => void
    onCancel: () => void
    onExpand: () => void
}

/**
 * 侧栏拖拽分隔条。
 *
 * 拖动帧只通过回调写 DOM，不更新侧栏宽度状态，避免整条侧栏每帧重渲染；
 * 折叠阈值在拖动过程中就会结算，不会先渲染出一个过窄的侧栏。
 */
export function SidebarResizer({
    width,
    max,
    collapsed,
    label,
    expandLabel,
    onStart,
    onResize,
    onCommit,
    onCancel,
    onExpand,
}: SidebarResizerProps) {
    const elementRef = useRef<HTMLDivElement | null>(null)
    const startXRef = useRef(0)
    const startWidthRef = useRef(width)
    const pendingDeltaRef = useRef(0)
    const frameIdRef = useRef(0)
    const pointerIdRef = useRef<number | null>(null)
    const isDraggingRef = useRef(false)
    // 拖动结束后浏览器会补发一次 click；在下一次按下前忽略，避免折叠被误触发为展开
    const blockNextClickRef = useRef(false)
    const finishRef = useRef<(mode: FinishMode) => void>(() => undefined)
    const [isDragging, setIsDragging] = useState(false)
    const [liveWidth, setLiveWidth] = useState(width)

    // 拖动期间才使用实时宽度，结束后立即回到父级提交值，避免两套来源打架
    const displayWidth = Math.round(isDragging ? liveWidth : width)

    const clampDragWidth = (value: number): number =>
        Math.min(Math.max(Math.round(value), SIDEBAR_LAYOUT.collapseThreshold), max)

    const releasePointer = (): void => {
        const element = elementRef.current
        const pointerId = pointerIdRef.current
        if (element && pointerId !== null && element.hasPointerCapture(pointerId)) {
            element.releasePointerCapture(pointerId)
        }
        pointerIdRef.current = null
    }

    const finish = (mode: FinishMode): void => {
        if (!isDraggingRef.current) {
            return
        }
        isDraggingRef.current = false
        blockNextClickRef.current = true
        document.body.classList.remove('select-none', 'cursor-col-resize')
        if (frameIdRef.current) {
            window.cancelAnimationFrame(frameIdRef.current)
            frameIdRef.current = 0
        }
        releasePointer()
        setIsDragging(false)

        if (mode === 'commit') {
            const finalWidth = clampDragWidth(startWidthRef.current + pendingDeltaRef.current)
            setLiveWidth(finalWidth)
            onResize(finalWidth)
            onCommit(finalWidth)
        } else {
            onCancel()
        }
        pendingDeltaRef.current = 0
    }

    // 窗口失焦与 Escape 只在拖动期间挂载，处理函数通过 ref 读取最新一次 finish
    useEffect(() => {
        finishRef.current = finish
    })

    useEffect(() => {
        if (!isDragging) {
            return
        }

        const handleBlur = (): void => finishRef.current('commit')
        const handleEscape = (event: KeyboardEvent): void => {
            if (event.key === 'Escape') {
                event.preventDefault()
                finishRef.current('cancel')
            }
        }

        window.addEventListener('blur', handleBlur)
        window.addEventListener('keydown', handleEscape)

        return () => {
            window.removeEventListener('blur', handleBlur)
            window.removeEventListener('keydown', handleEscape)
        }
    }, [isDragging])

    // 组件卸载时若仍在拖动，必须清掉全局类与帧，否则会污染下一个页面
    useEffect(
        () => () => {
            if (frameIdRef.current) {
                window.cancelAnimationFrame(frameIdRef.current)
                frameIdRef.current = 0
            }
            document.body.classList.remove('select-none', 'cursor-col-resize')
            const element = elementRef.current
            const pointerId = pointerIdRef.current
            if (element && pointerId !== null && element.hasPointerCapture(pointerId)) {
                element.releasePointerCapture(pointerId)
            }
            pointerIdRef.current = null
        },
        [],
    )

    const flushFrame = (): void => {
        frameIdRef.current = 0
        const next = clampDragWidth(startWidthRef.current + pendingDeltaRef.current)
        if (next <= SIDEBAR_LAYOUT.collapseThreshold) {
            setLiveWidth(next)
            finish('commit')
            return
        }
        setLiveWidth(next)
        onResize(next)
    }

    const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>): void => {
        if (collapsed) {
            // 折叠态边界是展开入口，新的一次按下代表独立点击
            blockNextClickRef.current = false
            return
        }
        if (event.button !== 0) {
            return
        }
        // 阻止默认行为，避免拖动时选中侧栏文字
        event.preventDefault()
        startXRef.current = event.clientX
        startWidthRef.current = width
        pendingDeltaRef.current = 0
        isDraggingRef.current = true
        pointerIdRef.current = event.pointerId

        const element = elementRef.current
        element?.setPointerCapture(event.pointerId)
        element?.focus()
        document.body.classList.add('select-none', 'cursor-col-resize')
        setIsDragging(true)
        onStart()
    }

    const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>): void => {
        if (!isDraggingRef.current) {
            return
        }
        pendingDeltaRef.current = event.clientX - startXRef.current
        if (frameIdRef.current) {
            return
        }
        // 用 rAF 合并高频 move，最后一帧在结束时单独结算，不会丢宽度
        frameIdRef.current = window.requestAnimationFrame(flushFrame)
    }

    const handleClick = (): void => {
        if (collapsed && !blockNextClickRef.current) {
            onExpand()
        }
    }

    const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>): void => {
        if (collapsed) {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                onExpand()
            }
            return
        }
        if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') {
            return
        }

        event.preventDefault()
        const step = event.shiftKey ? SIDEBAR_LAYOUT.keyboardLargeStep : SIDEBAR_LAYOUT.keyboardStep
        const direction = event.key === 'ArrowRight' ? 1 : -1
        const next = width + direction * step

        // 向左越过最小宽度时与鼠标一致，提交折叠
        if (direction < 0 && next < SIDEBAR_LAYOUT.minWidth) {
            onCommit(SIDEBAR_LAYOUT.collapseThreshold)
            return
        }
        onCommit(clampDragWidth(next))
    }

    return (
        <div
            ref={elementRef}
            data-sidebar-expand-edge
            role={collapsed ? 'button' : 'separator'}
            aria-orientation={collapsed ? undefined : 'vertical'}
            aria-label={collapsed ? expandLabel : label}
            aria-expanded={collapsed ? false : undefined}
            aria-valuemin={collapsed ? undefined : SIDEBAR_LAYOUT.minWidth}
            aria-valuemax={collapsed ? undefined : Math.round(max)}
            aria-valuenow={collapsed ? undefined : displayWidth}
            aria-valuetext={collapsed ? undefined : `${displayWidth}px`}
            tabIndex={0}
            className={cn(
                'group absolute inset-y-0 -right-[3px] z-20 w-1.5 touch-none outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-clay',
                collapsed ? 'cursor-pointer' : 'cursor-col-resize',
            )}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={() => finish('commit')}
            onPointerCancel={() => finish('cancel')}
            onLostPointerCapture={() => finish('commit')}
            onClick={handleClick}
            onKeyDown={handleKeyDown}
        >
            <span
                aria-hidden="true"
                className={cn(
                    'pointer-events-none absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-transparent transition-colors duration-150 group-focus-visible:bg-clay',
                    isDragging ? 'bg-clay' : collapsed ? 'group-hover:bg-clay' : 'group-hover:bg-border-strong',
                )}
            />
        </div>
    )
}
