import { STORAGE_KEYS } from '@/constants/storage'
import { createBrowserStore, type BrowserStore } from '@/shared/lib/browser-store'

/** 与服务端 chat 请求的 thread_id 约束一致：1..64 个字符 */
export const THREAD_ID_MAX_LENGTH = 64

const THREAD_ID_PREFIX = 'thread-'
const CHAT_PATH_PREFIX = '/chat/'

/** 兼容镜像随标签页结束失效，固定走 sessionStorage */
const sessionStore = createBrowserStore({ area: 'session' })
/** 草稿标记与服务端「首轮结束才创建会话」的生命周期一致，同样只存活当前标签页 */
const draftStore = createBrowserStore({ area: 'session' })

/** 调用方显式注入替身时按其走，否则复用模块级 session 存储 */
const withStorage = (storage?: Storage): BrowserStore =>
    storage ? createBrowserStore({ storage }) : sessionStore

const normalizeThreadId = (value: unknown): string | null => {
    if (typeof value !== 'string') {
        return null
    }

    const trimmed = value.trim()
    if (trimmed.length === 0 || trimmed.length > THREAD_ID_MAX_LENGTH) {
        return null
    }

    return trimmed
}

/**
 * 读取 `agent-thread` 兼容镜像。
 *
 * 与 Vue 基线一致：值必须是 `JSON.stringify(threadId)` 的字符串；
 * 非法 JSON、非字符串或空串一律当作没有值，避免损坏数据把页面带进错误会话。
 */
export const readAgentThreadId = (storage?: Storage): string | null =>
    // 存储被禁用或内容损坏时按「没有镜像」处理，不阻断会话创建
    normalizeThreadId(withStorage(storage).readJson<unknown>(STORAGE_KEYS.agentThread))

/** 只写兼容镜像，不构成权威状态；URL 仍然是会话的唯一来源 */
export const writeAgentThreadId = (threadId: string, storage?: Storage): void => {
    const normalized = normalizeThreadId(threadId)
    if (!normalized) {
        return
    }

    // 写入失败只影响兼容回读，不影响当前会话
    withStorage(storage).writeJson(STORAGE_KEYS.agentThread, normalized)
}

/** 非安全上下文没有 randomUUID 时退回时间戳 + 随机串，仍满足 1..64 长度约束 */
export const createThreadId = (): string => {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
        return crypto.randomUUID()
    }

    return `${THREAD_ID_PREFIX}${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

export interface ResolveSessionOptions {
    readonly sessionId?: string | null
    readonly storage?: Storage
}

/** 会话 ID 的来源，决定会话是否已经存在于服务端 */
export type SessionThreadSource = 'url' | 'mirror' | 'generated'

export interface ResolvedSessionThread {
    readonly threadId: string
    readonly source: SessionThreadSource
}

/**
 * 解析会话 ID 及其来源。
 *
 * URL 中的有效 ID 优先；缺失时回退 `agent-thread` 镜像（兼容 Vue 期间写入的值）；
 * 两者都没有则生成新 ID。只有 `generated` 才是尚未落库的草稿会话，
 * 调用方不得对其发起历史查询。
 */
export const resolveSessionThread = (
    options: ResolveSessionOptions = {},
): ResolvedSessionThread => {
    const fromUrl = normalizeThreadId(options.sessionId)
    if (fromUrl) {
        return { threadId: fromUrl, source: 'url' }
    }

    const fromMirror = readAgentThreadId(options.storage)
    if (fromMirror) {
        return { threadId: fromMirror, source: 'mirror' }
    }

    return { threadId: createThreadId(), source: 'generated' }
}

/** 草稿只保留最近几个：StrictMode 会重复执行渲染，可能生成多个未提交的 ID */
const DRAFT_THREAD_LIMIT = 5

const readDraftThreads = (): readonly string[] => {
    const value = draftStore.readJson<unknown>(STORAGE_KEYS.agentDraftThread)
    return Array.isArray(value)
        ? value.filter((item): item is string => normalizeThreadId(item) !== null)
        : []
}

/**
 * 登记尚未落库的草稿会话。
 *
 * 服务端在首轮结束前没有 `session_meta` 记录，此时查询历史必然 404，
 * 骨架屏与错误提示都属于假状态；登记后由查询门控跳过。
 */
export const markDraftThread = (threadId: string): void => {
    const normalized = normalizeThreadId(threadId)
    if (!normalized) {
        return
    }

    const next = [...readDraftThreads().filter((item) => item !== normalized), normalized]
    draftStore.writeJson(STORAGE_KEYS.agentDraftThread, next.slice(-DRAFT_THREAD_LIMIT))
}

export const isDraftThread = (threadId: string): boolean => {
    const normalized = normalizeThreadId(threadId)
    return normalized !== null && readDraftThreads().includes(normalized)
}

/** 服务端确认落库后调用；只清理当前 ID，未提交的其它草稿不受影响 */
export const clearDraftThread = (threadId: string): void => {
    const normalized = normalizeThreadId(threadId)
    if (normalized === null) {
        return
    }

    const remaining = readDraftThreads().filter((item) => item !== normalized)
    if (remaining.length === 0) {
        draftStore.remove(STORAGE_KEYS.agentDraftThread)
        return
    }

    draftStore.writeJson(STORAGE_KEYS.agentDraftThread, remaining)
}

/** 规范地址；动态段需要编码，避免特殊字符破坏路由匹配 */
export const toChatPath = (threadId: string): string =>
    `${CHAT_PATH_PREFIX}${encodeURIComponent(threadId.trim())}`
