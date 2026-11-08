import { queryOptions } from '@tanstack/react-query'

import { queryKeys } from '@/shared/lib/query-keys'

import { listModelConnections, listModelProviders, listModels } from './models'

/** 可接入 Provider 目录：设置页的供应商选择与模型数量来源，404 表示运行时未启用 */
export const modelProvidersQueryOptions = queryOptions({
  queryKey: queryKeys.models.providers,
  queryFn: () => listModelProviders(),
})

/** 模型目录：Provider 选项与对话页的模型选择共用，404 表示运行时未启用 */
export const modelCatalogQueryOptions = queryOptions({
  queryKey: queryKeys.models.catalog,
  // 包一层再调用：queryFn 会被传入 QueryFunctionContext，不能直接当分页参数用
  queryFn: () => listModels(),
})

/** BYOK 连接列表；创建、验证与删除后统一失效该 key */
export const modelConnectionsQueryOptions = queryOptions({
  queryKey: queryKeys.models.connections,
  queryFn: () => listModelConnections(),
})
