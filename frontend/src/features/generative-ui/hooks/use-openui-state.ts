import { useCallback, useMemo } from 'react'

import { createBrowserStore } from '@/shared/lib/browser-store'

import type { OpenUiStateRecord } from '../types'

/** 状态结构变更时递增版本，旧结构直接丢弃而不是错误恢复 */
const STATE_VERSION = 1

/** 缓存上限只用于防止长会话无限增长，超出后按写入顺序淘汰最旧块 */
const MAX_CACHED_BLOCKS = 100

/** 键前缀包含版本，避免旧版本记录被误读；版本同时写入记录体做二次校验 */
const STORAGE_PREFIX = `openui-state:v${STATE_VERSION}:`

/** 表单状态只随标签页存活，固定走 sessionStorage，命名空间即版本前缀 */
const stateStore = createBrowserStore({ area: 'session', prefix: STORAGE_PREFIX })

/**
 * FNV-1a 32 位哈希。
 *
 * 这里只需要稳定、低碰撞的键，不用于安全用途；同步实现避免表单初始化变成异步。
 */
const hashContent = (content: string): string => {
  let hash = 0x811c9dc5
  for (let index = 0; index < content.length; index += 1) {
    hash ^= content.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193)
  }
  return (hash >>> 0).toString(36)
}

const buildStateKey = (threadId: string, content: string): string =>
  `${threadId}:${hashContent(content)}`

const isPlainRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const readState = (stateKey: string): Record<string, unknown> | undefined => {
  // 存储被禁用或内容损坏时 readJson 返回 undefined，渲染继续使用默认值
  const parsed = stateStore.readJson<unknown>(stateKey)
  if (!isPlainRecord(parsed) || parsed.version !== STATE_VERSION || !isPlainRecord(parsed.values)) {
    // 版本不匹配或内容损坏：旧结构直接丢弃，顺带清理损坏残留
    stateStore.remove(stateKey)
    return undefined
  }

  // 返回浅拷贝，避免渲染层直接改到存储中的对象
  return { ...parsed.values }
}

/** 超出上限时按写入顺序淘汰最旧的块 */
const pruneStorage = (): void => {
  const stateKeys = stateStore.keys()
  const excessCount = stateKeys.length - MAX_CACHED_BLOCKS
  for (let index = 0; index < excessCount; index += 1) {
    const key = stateKeys[index]
    if (key !== undefined) {
      stateStore.remove(key)
    }
  }
}

const writeState = (stateKey: string, values: Record<string, unknown>): void => {
  const record: OpenUiStateRecord = { version: STATE_VERSION, values: { ...values } }

  // 配额耗尽或隐私模式写入失败时不再淘汰，避免用一次失败写入触发额外删除
  if (stateStore.writeJson(stateKey, record)) {
    pruneStorage()
  }
}

export interface UseOpenUiStateResult {
  readonly initialState: Record<string, unknown> | undefined
  readonly handleStateUpdate: (state: Record<string, unknown>) => void
}

/**
 * 单个 OpenUI 块的表单状态缓存。
 *
 * 实时消息完成后会被历史消息替换并重新挂载，键固定为「会话 + 块内容哈希」，
 * 因此重挂载与页面刷新都能恢复用户已填内容。状态只存 sessionStorage：
 * 关闭标签页即丢弃，不同步服务端，也不跨设备恢复（依据 ADR-0003 D-03）。
 */
export function useOpenUiState(threadId: string, content: string): UseOpenUiStateResult {
  const stateKey = useMemo(() => buildStateKey(threadId, content), [threadId, content])
  const initialState = useMemo(() => readState(stateKey), [stateKey])

  const handleStateUpdate = useCallback(
    (state: Record<string, unknown>): void => {
      writeState(stateKey, state)
    },
    [stateKey],
  )

  return { initialState, handleStateUpdate }
}
