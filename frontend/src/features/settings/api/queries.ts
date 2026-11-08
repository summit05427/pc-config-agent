import { queryOptions } from '@tanstack/react-query'

import { getProfile, listDeviceSessions } from '@/features/auth/api'
import { queryKeys } from '@/shared/lib/query-keys'

import { getPreferences } from './preferences'

/** Agent 偏好：设置页与后续对话共用同一份缓存 */
export const preferencesQueryOptions = queryOptions({
  queryKey: queryKeys.settings.preferences,
  queryFn: getPreferences,
})

/** 个人资料：保存后失效该 key，表单再以服务端返回值为准重新挂载 */
export const profileQueryOptions = queryOptions({
  queryKey: queryKeys.settings.profile,
  queryFn: getProfile,
})

/** 设备会话一次取满后端上限，组件内用固定高度滚动，不再分页 */
const DEVICE_SESSIONS_SIZE = 100

/** 登录设备列表，固定 key 供撤销后统一失效 */
export const deviceSessionsQueryOptions = () =>
  queryOptions({
    queryKey: queryKeys.settings.deviceSessionsAll,
    queryFn: () => listDeviceSessions({ page: 1, size: DEVICE_SESSIONS_SIZE }),
  })
