/**
 * TanStack Query 的 key 集中登记处。
 *
 * 每个域都有 `all` 前缀，失效时按前缀批量 invalidate；
 * 列表 key 在各域 api 中以 `[...all, 'list', params]` 形式生成，
 * 保证 queryFn 依赖的参数全部参与缓存命中。
 */
export const queryKeys = {
  adminUsers: {
    all: ['admin-users'] as const,
  },
  auditLogs: {
    all: ['audit-logs'] as const,
  },
  adminModels: {
    all: ['admin-models'] as const,
  },
  modelProviders: {
    all: ['model-providers'] as const,
  },
  adminUsage: {
    all: ['admin-usage'] as const,
  },
  adminConnections: {
    all: ['admin-connections'] as const,
  },
  adminFeedback: {
    all: ['admin-feedback'] as const,
  },
}
