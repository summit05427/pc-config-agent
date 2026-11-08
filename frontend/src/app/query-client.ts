import { QueryClient } from '@tanstack/react-query'

import { isRetriableError, normalizeError } from '@/core/http'

// 服务端 5xx 与网络异常最多重试 2 次；4xx 与 401 不重试，401 由请求层单飞刷新处理
const MAX_RETRIES = 2
const STALE_TIME = 30_000
const GC_TIME = 5 * 60 * 1000

/**
 * 创建应用级 QueryClient。
 *
 * 抽成工厂函数便于单测使用独立缓存，避免用例之间共享查询状态。
 * 错误统一经 `normalizeError` 判定是否为可重试的 ApiError。
 */
export const createQueryClient = (): QueryClient =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: (failureCount, error) =>
          failureCount < MAX_RETRIES && isRetriableError(normalizeError(error)),
        staleTime: STALE_TIME,
        gcTime: GC_TIME,
      },
      mutations: {
        // 写请求不做自动重试；需要幂等的场景由调用方显式传 Idempotency-Key
        retry: 0,
      },
    },
  })

export const queryClient = createQueryClient()
