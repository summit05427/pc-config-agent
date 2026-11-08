/**
 * 侧边栏尺寸与拖拽参数。
 * 与 `docs/services/frontend/ui-design-system.md` 第 4 节及 `--app-sidebar-*` 变量保持一致。
 */
export const SIDEBAR_LAYOUT = {
    /** 默认展开宽度，沿用 CDS 的 288px */
    defaultWidth: 288,
    /** 正常展开状态的最小宽度，保证导航与会话标题可读 */
    minWidth: 220,
    /** 展开宽度上限，实际值还会受 40vw 视口比例约束 */
    maxWidth: 420,
    maxViewportRatio: 0.4,
    /** 拖到该宽度即触发折叠，不需要等到松开鼠标；与最小宽度是两个概念 */
    collapseThreshold: 200,
    /** 折叠后的导航栏宽度 */
    railWidth: 56,
    /** 分隔条命中宽度，视觉只画 1px 发丝线 */
    resizerHitWidth: 6,
    keyboardStep: 16,
    keyboardLargeStep: 48,
} as const

/**
 * 将宽度限制在“正常展开”区间。
 * 视口较小时 maxWidth 可能接近甚至小于最小宽度，因此先夹最大值再夹最小值。
 */
export function clampExpandedWidth(width: number, maxWidth: number): number {
    if (!Number.isFinite(width)) {
        return SIDEBAR_LAYOUT.defaultWidth
    }

    const safeMax = Math.max(SIDEBAR_LAYOUT.minWidth, maxWidth)
    return Math.min(Math.max(Math.round(width), SIDEBAR_LAYOUT.minWidth), safeMax)
}

/** 视口允许的最大展开宽度：不超过 420px，也不超过 40vw，且不小于最小宽度 */
export function resolveSidebarMaxWidth(viewportWidth: number): number {
    const ratioLimit = Math.floor(viewportWidth * SIDEBAR_LAYOUT.maxViewportRatio)
    return Math.min(SIDEBAR_LAYOUT.maxWidth, Math.max(SIDEBAR_LAYOUT.minWidth, ratioLimit))
}

export interface SidebarCommit {
    collapsed: boolean
    width: number
}

/**
 * 拖动结束后的提交规则：
 * - 小于等于折叠阈值：折叠；
 * - 大于阈值但小于普通最小宽度：吸附到最小宽度；
 * - 其余：保留用户宽度并夹到上限。
 */
export function resolveSidebarCommit(width: number, maxWidth: number): SidebarCommit {
    if (!Number.isFinite(width) || width <= SIDEBAR_LAYOUT.collapseThreshold) {
        return { collapsed: true, width: SIDEBAR_LAYOUT.defaultWidth }
    }

    return { collapsed: false, width: clampExpandedWidth(width, maxWidth) }
}
