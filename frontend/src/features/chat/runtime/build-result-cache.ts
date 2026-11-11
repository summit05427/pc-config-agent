import type { BuildResult } from '@/features/sessions/api'

interface CachedBuildResult {
    readonly content: string
    readonly buildResult: BuildResult
}

/** 只保留最近若干个会话，避免长时间使用后无上限增长 */
const MAX_CACHED_SESSIONS = 20

/** sessionStorage 前缀：同一标签页刷新后仍能恢复详情数据，关闭标签页即失效 */
const STORAGE_PREFIX = 'openui:build-result:'

/**
 * 单会话最近一次结构化结果缓存。
 *
 * `done` 之后交接会用服务端历史替换临时消息，历史响应不含 build_result。
 * 这里按「会话 + 回答正文」暂存，历史映射时命中同一条回答就恢复卡片与详情按钮；
 * 同时写入 sessionStorage，刷新页面后不会因为内存缓存丢失而让详情按钮失效。
 */
const cache = new Map<string, CachedBuildResult>()

const canUseStorage = (): boolean => typeof window !== 'undefined' && 'sessionStorage' in window

const readFromStorage = (threadId: string): CachedBuildResult | undefined => {
    if (!canUseStorage()) {
        return undefined
    }

    try {
        const raw = window.sessionStorage.getItem(`${STORAGE_PREFIX}${threadId}`)
        if (!raw) {
            return undefined
        }
        const parsed = JSON.parse(raw) as Partial<CachedBuildResult>
        if (typeof parsed.content !== 'string' || !parsed.buildResult) {
            return undefined
        }
        return { content: parsed.content, buildResult: parsed.buildResult }
    } catch {
        // 隐私模式或存储被禁用：退回纯内存缓存
        return undefined
    }
}

const writeToStorage = (threadId: string, entry: CachedBuildResult): void => {
    if (!canUseStorage()) {
        return
    }

    try {
        window.sessionStorage.setItem(`${STORAGE_PREFIX}${threadId}`, JSON.stringify(entry))
    } catch {
        // 容量不足或被禁用时不影响主流程
    }
}

const removeFromStorage = (threadId: string): void => {
    if (!canUseStorage()) {
        return
    }

    try {
        window.sessionStorage.removeItem(`${STORAGE_PREFIX}${threadId}`)
    } catch {
        // 忽略存储异常
    }
}

export function rememberBuildResult(
    threadId: string,
    content: string,
    buildResult: BuildResult,
): void {
    const entry = { content, buildResult }
    cache.delete(threadId)
    cache.set(threadId, entry)
    writeToStorage(threadId, entry)

    if (cache.size > MAX_CACHED_SESSIONS) {
        const oldestKey = cache.keys().next().value
        if (oldestKey !== undefined) {
            cache.delete(oldestKey)
            // 存储层与内存层保持一致，否则淘汰的会话仍会被读出来
            removeFromStorage(oldestKey)
        }
    }
}

export function readBuildResult(threadId: string, content: string): BuildResult | undefined {
    const entry = cache.get(threadId) ?? readFromStorage(threadId)
    if (!entry) {
        return undefined
    }

    // 末尾换行等空白差异不应导致详情按钮失效，按 trim 后比较
    return entry.content.trim() === content.trim() ? entry.buildResult : undefined
}

export function forgetBuildResult(threadId: string): void {
    cache.delete(threadId)
    removeFromStorage(threadId)
}
