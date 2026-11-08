import { queryOptions } from '@tanstack/react-query'

import { queryKeys } from '@/shared/lib/query-keys'

import { getCurrentUser } from './auth'

// 用户资料在会话有效期内很少变化，5 分钟内不重复请求；
// 认证会话切换时会整体清空缓存，不会读到上一个账号的数据
const CURRENT_USER_STALE_TIME = 5 * 60 * 1000

/** 当前用户查询：路由守卫用 ensureQueryData 预热，页面用 useQuery 订阅同一份缓存 */
export const currentUserQueryOptions = queryOptions({
  queryKey: queryKeys.auth.currentUser,
  queryFn: getCurrentUser,
  staleTime: CURRENT_USER_STALE_TIME,
})
