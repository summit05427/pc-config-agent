import { describe, expect, it } from 'vitest'

import { createBrowserStore } from './browser-store'

/** 内存版 Storage：键顺序与原生一致，便于验证按写入顺序淘汰的行为 */
const createMemoryStorage = (): Storage => {
  const entries = new Map<string, string>()

  return {
    get length(): number {
      return entries.size
    },
    key: (index: number): string | null => Array.from(entries.keys())[index] ?? null,
    getItem: (key: string): string | null => entries.get(key) ?? null,
    setItem: (key: string, value: string): void => {
      entries.set(key, value)
    },
    removeItem: (key: string): void => {
      entries.delete(key)
    },
    clear: (): void => {
      entries.clear()
    },
  }
}

/** 隐私模式或配额耗尽：所有访问都抛错，验证策略层不向外传播异常 */
const createBlockedStorage = (): Storage => ({
  get length(): number {
    throw new Error('storage blocked')
  },
  key: (): string | null => {
    throw new Error('storage blocked')
  },
  getItem: (): string | null => {
    throw new Error('storage blocked')
  },
  setItem: (): void => {
    throw new Error('storage blocked')
  },
  removeItem: (): void => {
    throw new Error('storage blocked')
  },
  clear: (): void => {
    throw new Error('storage blocked')
  },
})

describe('createBrowserStore', () => {
  it('写入后可按原结构读回', () => {
    const store = createBrowserStore({ storage: createMemoryStorage() })

    expect(store.writeJson('prefs', { theme: 'dark', sidebarWidth: 320 })).toBe(true)
    expect(store.readJson('prefs')).toEqual({ theme: 'dark', sidebarWidth: 320 })
  })

  it('键不存在、内容损坏或非 JSON 文本都返回 undefined', () => {
    const storage = createMemoryStorage()
    const store = createBrowserStore({ storage })
    storage.setItem('broken', '{not-json')

    expect(store.readJson('missing')).toBeUndefined()
    expect(store.readJson('broken')).toBeUndefined()
  })

  it('写入失败返回 false 且不抛出', () => {
    const store = createBrowserStore({ storage: createBlockedStorage() })

    expect(() => store.writeJson('prefs', { theme: 'dark' })).not.toThrow()
    expect(store.writeJson('prefs', { theme: 'dark' })).toBe(false)
  })

  it('存储不可用时读取、删除与枚举都安全降级', () => {
    const store = createBrowserStore({ storage: createBlockedStorage() })

    expect(store.readJson('prefs')).toBeUndefined()
    expect(store.keys()).toEqual([])
    expect(() => store.remove('prefs')).not.toThrow()
  })

  it('前缀隔离命名空间，keys 返回去掉前缀的相对键', () => {
    const storage = createMemoryStorage()
    const store = createBrowserStore({ storage, prefix: 'openui:v1:' })
    store.writeJson('thread-a:1', { value: 1 })
    store.writeJson('thread-b:2', { value: 2 })
    storage.setItem('unrelated', 'x')

    expect(store.keys()).toEqual(['thread-a:1', 'thread-b:2'])
    expect(storage.getItem('openui:v1:thread-a:1')).not.toBeNull()
    expect(storage.getItem('unrelated')).toBe('x')
  })

  it('namespace 累加前缀，父子命名空间互不干扰', () => {
    const storage = createMemoryStorage()
    const parent = createBrowserStore({ storage, prefix: 'app:' })
    const child = parent.namespace('chat:')

    child.writeJson('draft', 'hello')

    expect(storage.getItem('app:chat:draft')).toBe(JSON.stringify('hello'))
    expect(child.readJson('draft')).toBe('hello')
    expect(parent.keys()).toEqual(['chat:draft'])
    expect(parent.readJson('draft')).toBeUndefined()
  })

  it('remove 删除指定键，不影响同命名空间的其他键', () => {
    const storage = createMemoryStorage()
    const store = createBrowserStore({ storage, prefix: 'openui:v1:' })
    store.writeJson('thread-a:1', { value: 1 })
    store.writeJson('thread-b:2', { value: 2 })

    store.remove('thread-a:1')

    expect(store.keys()).toEqual(['thread-b:2'])
  })
})
