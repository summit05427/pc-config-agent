/**
 * TanStack Query 的 key 唯一登记处。
 *
 * 按领域分组，查询与失效都引用常量，禁止在组件里手写数组字面量；
 * 同一份服务端数据只允许有一个 key，避免缓存出现两个权威来源。
 */
export const queryKeys = {
  auth: {
    all: ['auth'] as const,
    currentUser: ['auth', 'current-user'] as const,
  },
  models: {
    all: ['models'] as const,
    catalog: ['models', 'catalog'] as const,
    connections: ['models', 'connections'] as const,
    providers: ['models', 'providers'] as const,
  },
  sessions: {
    all: ['sessions'] as const,
    /** 前缀 key：失效所有会话列表（含默认与归档） */
    lists: ['sessions', 'list'] as const,
    list: (page: number, size: number, archived = false) =>
      ['sessions', 'list', page, size, archived] as const,
    /** 前缀 key：invalidate 时命中该会话的所有分页与排序组合 */
    messagesAll: (threadId: string) => ['sessions', 'messages', threadId] as const,
    messages: (threadId: string, page: number, size: number, order: string) =>
      ['sessions', 'messages', threadId, page, size, order] as const,
  },
  settings: {
    all: ['settings'] as const,
    preferences: ['settings', 'preferences'] as const,
    profile: ['settings', 'profile'] as const,
    deviceSessionsAll: ['settings', 'device-sessions'] as const,
  },
  usage: {
    all: ['usage'] as const,
    modelUsage: (query: object) => ['usage', 'model-usage', query] as const,
  },
} as const
