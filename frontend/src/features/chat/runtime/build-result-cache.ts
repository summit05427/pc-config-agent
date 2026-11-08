import type { BuildResult } from '@/features/sessions/api'

interface CachedBuildResult {
    readonly content: string
    readonly buildResult: BuildResult
}

/** 只保留最近若干个会话，避免长时间使用后无上限增长 */
const MAX_CACHED_SESSIONS = 20

/**
 * 单会话最近一次结构化结果的内存缓存。
 *
 * `done` 之后交接会用服务端历史替换临时消息，历史响应不含 build_result。
 * 这里按「会话 + 回答正文」暂存，历史映射时命中同一条回答就恢复卡片；
 * 刷新页面后缓存为空，自然回退到 Markdown，不影响历史可回放。
 */
const cache = new Map<string, CachedBuildResult>()

export function rememberBuildResult(
    threadId: string,
    content: string,
    buildResult: BuildResult,
): void {
    cache.delete(threadId)
    cache.set(threadId, { content, buildResult })

    if (cache.size > MAX_CACHED_SESSIONS) {
        const oldestKey = cache.keys().next().value
        if (oldestKey !== undefined) {
            cache.delete(oldestKey)
        }
    }
}

export function readBuildResult(threadId: string, content: string): BuildResult | undefined {
    const entry = cache.get(threadId)
    return entry && entry.content === content ? entry.buildResult : undefined
}

export function forgetBuildResult(threadId: string): void {
    cache.delete(threadId)
}
