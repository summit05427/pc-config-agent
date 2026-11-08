/** 原生存储区域；只在未显式注入 `storage` 时用于定位 `window` 上的实现 */
export type StorageArea = 'local' | 'session'

export interface BrowserStoreOptions {
  /** 缺省 `local`；显式传入 `storage` 时该字段被忽略 */
  readonly area?: StorageArea
  /** 注入替身：单测传内存实现即可，无需触碰浏览器全局 */
  readonly storage?: Storage
  /** 命名空间前缀，自动附加到每个键；`keys()` 返回去掉前缀的相对键 */
  readonly prefix?: string
}

/**
 * 浏览器存储的唯一策略层。
 *
 * 各域只需关心键的构造、结构校验与淘汰规则；读写异常、JSON 编解码、
 * 隐私模式与配额耗尽导致的读写失败统一在这里降级为「没有值 / 写入失败」，
 * 调用方永远不需要包 `try/catch`，也不会因为存储不可用阻断界面交互。
 */
export interface BrowserStore {
  /** 读取并解析 JSON；键不存在、内容损坏或存储不可用都返回 `undefined` */
  readonly readJson: <T>(key: string) => T | undefined
  /** 序列化后写入；成功返回 `true`，配额耗尽或存储不可用时返回 `false` */
  readonly writeJson: (key: string, value: unknown) => boolean
  readonly remove: (key: string) => void
  /** 属于当前命名空间的相对键，按存储的键顺序返回（即写入顺序） */
  readonly keys: () => readonly string[]
  /** 派生子命名空间，前缀累加 */
  readonly namespace: (prefix: string) => BrowserStore
}

/** 延迟解析而非创建时快照：非浏览器环境与延迟初始化的 `window` 都能正确降级 */
const resolveStorage = (options: BrowserStoreOptions): Storage | null => {
  if (options.storage) {
    return options.storage
  }

  try {
    return (options.area ?? 'local') === 'session' ? window.sessionStorage : window.localStorage
  } catch {
    return null
  }
}

export function createBrowserStore(options: BrowserStoreOptions = {}): BrowserStore {
  const prefix = options.prefix ?? ''

  const readJson = <T>(key: string): T | undefined => {
    const storage = resolveStorage(options)
    if (!storage) {
      return undefined
    }

    try {
      const raw = storage.getItem(`${prefix}${key}`)
      return raw === null ? undefined : (JSON.parse(raw) as T)
    } catch {
      return undefined
    }
  }

  const writeJson = (key: string, value: unknown): boolean => {
    const storage = resolveStorage(options)
    if (!storage) {
      return false
    }

    try {
      storage.setItem(`${prefix}${key}`, JSON.stringify(value))
      return true
    } catch {
      return false
    }
  }

  const remove = (key: string): void => {
    const storage = resolveStorage(options)
    if (!storage) {
      return
    }

    try {
      storage.removeItem(`${prefix}${key}`)
    } catch {
      // 删除失败只会留下过期条目，不影响当前交互
    }
  }

  const keys = (): readonly string[] => {
    const storage = resolveStorage(options)
    if (!storage) {
      return []
    }

    const result: string[] = []
    try {
      for (let index = 0; index < storage.length; index += 1) {
        const fullKey = storage.key(index)
        if (fullKey?.startsWith(prefix)) {
          result.push(fullKey.slice(prefix.length))
        }
      }
    } catch {
      return []
    }

    return result
  }

  const namespace = (childPrefix: string): BrowserStore =>
    createBrowserStore({ ...options, prefix: `${prefix}${childPrefix}` })

  return { readJson, writeJson, remove, keys, namespace }
}
