import { useEffect, useState } from 'react'

/** 视口宽度：侧栏展开上限依赖它，缩窗时实际宽度需要跟着收缩 */
export function useViewportWidth(): number {
    const [viewportWidth, setViewportWidth] = useState<number>(() => window.innerWidth)

    useEffect(() => {
        // resize 高频触发，用 rAF 合并成每帧最多一次 setState
        let frameId = 0

        const handleResize = (): void => {
            if (frameId) {
                return
            }

            frameId = window.requestAnimationFrame(() => {
                frameId = 0
                setViewportWidth(window.innerWidth)
            })
        }

        window.addEventListener('resize', handleResize)

        return () => {
            window.removeEventListener('resize', handleResize)
            if (frameId) {
                window.cancelAnimationFrame(frameId)
            }
        }
    }, [])

    return viewportWidth
}
