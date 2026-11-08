import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { STORAGE_KEYS } from '@/constants/storage'

import {
    THREAD_ID_MAX_LENGTH,
    clearDraftThread,
    createThreadId,
    isDraftThread,
    markDraftThread,
    readAgentThreadId,
    resolveSessionThread,
    toChatPath,
    writeAgentThreadId,
} from './agent-thread'

const readRaw = (): string | null => window.sessionStorage.getItem(STORAGE_KEYS.agentThread)

const readValue = (): unknown => JSON.parse(readRaw() ?? 'null') as unknown

/** 模拟隐私模式或配额耗尽：读写都抛错，验证降级不阻断会话 */
const createBlockedStorage = (): Storage =>
    ({
        getItem: () => {
            throw new Error('storage blocked')
        },
        setItem: () => {
            throw new Error('storage blocked')
        },
    }) as unknown as Storage

beforeEach(() => {
    window.sessionStorage.clear()
})

afterEach(() => {
    vi.unstubAllGlobals()
})

describe('agent-thread 兼容镜像', () => {
    it('写入格式与 Vue 基线一致：JSON.stringify(threadId)', () => {
        writeAgentThreadId('thread-1')

        expect(readRaw()).toBe('"thread-1"')
        expect(readValue()).toBe('thread-1')
        expect(readAgentThreadId()).toBe('thread-1')
    })

    it('读取时容错非法 JSON、非字符串、空串与超长值', () => {
        window.sessionStorage.setItem(STORAGE_KEYS.agentThread, '{broken')
        expect(readAgentThreadId()).toBeNull()

        window.sessionStorage.setItem(STORAGE_KEYS.agentThread, '123')
        expect(readAgentThreadId()).toBeNull()

        window.sessionStorage.setItem(STORAGE_KEYS.agentThread, '""')
        expect(readAgentThreadId()).toBeNull()

        window.sessionStorage.setItem(
            STORAGE_KEYS.agentThread,
            JSON.stringify('x'.repeat(THREAD_ID_MAX_LENGTH + 1)),
        )
        expect(readAgentThreadId()).toBeNull()
    })

    it('存储被禁用时读写都不抛出', () => {
        const storage = createBlockedStorage()

        expect(readAgentThreadId(storage)).toBeNull()
        expect(() => writeAgentThreadId('thread-1', storage)).not.toThrow()
    })

    it('空值或超长值不写入镜像', () => {
        writeAgentThreadId('   ')

        expect(readRaw()).toBeNull()
    })

    it('读取到首尾空白时做规范化', () => {
        window.sessionStorage.setItem(STORAGE_KEYS.agentThread, JSON.stringify('  thread-2  '))

        expect(readAgentThreadId()).toBe('thread-2')
    })
})

describe('会话 ID 解析', () => {
    it('URL 中的有效 ID 优先于镜像', () => {
        window.sessionStorage.setItem(STORAGE_KEYS.agentThread, JSON.stringify('thread-mirror'))

        expect(resolveSessionThread({ sessionId: ' thread-url ' })).toEqual({
            threadId: 'thread-url',
            source: 'url',
        })
    })

    it('URL 缺失时回退镜像值', () => {
        window.sessionStorage.setItem(STORAGE_KEYS.agentThread, JSON.stringify('thread-mirror'))

        expect(resolveSessionThread({ sessionId: undefined })).toEqual({
            threadId: 'thread-mirror',
            source: 'mirror',
        })
    })

    it('URL 与镜像都缺失时生成新 ID，且满足服务端长度约束', () => {
        const first = resolveSessionThread()
        const second = resolveSessionThread()

        expect(first.source).toBe('generated')
        expect(first.threadId.length).toBeGreaterThan(0)
        expect(first.threadId.length).toBeLessThanOrEqual(THREAD_ID_MAX_LENGTH)
        expect(first.threadId).not.toBe(second.threadId)
    })

    it('非安全上下文没有 randomUUID 时退回时间戳 + 随机串', () => {
        vi.stubGlobal('crypto', {})

        const threadId = createThreadId()

        expect(threadId.startsWith('thread-')).toBe(true)
        expect(threadId.length).toBeLessThanOrEqual(THREAD_ID_MAX_LENGTH)
    })

    it('规范地址对动态段做编码', () => {
        expect(toChatPath('thread/1')).toBe('/chat/thread%2F1')
        expect(toChatPath('  thread-1  ')).toBe('/chat/thread-1')
    })
})

describe('草稿会话标记', () => {
    it('登记后命中，清理后不再命中', () => {
        markDraftThread('thread-draft')

        expect(isDraftThread('thread-draft')).toBe(true)
        expect(isDraftThread('thread-other')).toBe(false)
        expect(isDraftThread('  thread-draft  ')).toBe(true)

        clearDraftThread('thread-other')
        expect(isDraftThread('thread-draft')).toBe(true)

        clearDraftThread('thread-draft')
        expect(isDraftThread('thread-draft')).toBe(false)
    })

    it('空值或超长 ID 不登记，也不会误删已有标记', () => {
        markDraftThread('   ')
        markDraftThread('x'.repeat(THREAD_ID_MAX_LENGTH + 1))

        expect(isDraftThread('   ')).toBe(false)
        expect(isDraftThread('x'.repeat(THREAD_ID_MAX_LENGTH + 1))).toBe(false)
    })
})
