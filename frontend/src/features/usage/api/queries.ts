import { queryOptions } from '@tanstack/react-query'

import { queryKeys } from '@/shared/lib/query-keys'

import { getMyModelUsage, type ModelUsageQuery } from './model-usage'

/** 用量查询：日期与分页都在 key 里，切换筛选时不会读到上一组条件的缓存 */
export const modelUsageQueryOptions = (query: ModelUsageQuery) =>
  queryOptions({
    queryKey: queryKeys.usage.modelUsage(query),
    queryFn: () => getMyModelUsage(query),
  })
