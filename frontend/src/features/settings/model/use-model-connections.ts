import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import { normalizeError } from '@/core/http'
import {
  createModelConnection,
  deleteModelConnection,
  modelCatalogQueryOptions,
  modelConnectionsQueryOptions,
  modelProvidersQueryOptions,
  updateModelConnection,
  verifyModelConnection,
  type ModelCatalogItem,
  type ModelConnection,
  type ModelConnectionCreatePayload,
  type ModelConnectionUpdatePayload,
  type ModelProviderSummary,
} from '@/features/models/api'
import { queryKeys } from '@/shared/lib/query-keys'

/**
 * 服务端明确表示「能力未启用」的业务码：
 * 40204 运行时总开关关闭、40209 BYOK 关闭。其它错误（404 路由缺失、5xx、网络）
 * 属于加载失败，不能误报成「未启用」。
 */
const FEATURE_DISABLED_CODES = new Set([40204, 40209])

const isFeatureDisabledError = (error: unknown): boolean =>
  FEATURE_DISABLED_CODES.has(Number(normalizeError(error).code))

/** 详情视图需要的只读数据与派生状态 */
export interface ModelConnectionsData {
  catalog: readonly ModelCatalogItem[]
  connections: readonly ModelConnection[]
  providers: readonly ModelProviderSummary[]
  /** 供应商 code 列表，供选择视图渲染 */
  providerCodes: readonly string[]
  /** 以 Provider 目录为准的模型数量，避免目录未加载时误判为 0 */
  modelCounts: ReadonlyMap<string, number>
  configuredProviderCodes: ReadonlySet<string>
  isLoading: boolean
  /** 服务端明确返回未启用业务码，整块降级为提示 */
  isUnavailable: boolean
  /** 除「未启用」外的任何查询错误，展示重试入口 */
  isLoadError: boolean
}

/** 生命周期操作：唯一知道「哪些缓存要失效、什么时候提示」的地方 */
export interface ModelConnectionsActions {
  verify: (connectionId: string) => Promise<void>
  rotate: (connectionId: string, payload: ModelConnectionUpdatePayload) => Promise<void>
  /** 失败时抛出 ApiError，由调用方决定是否停留在当前视图 */
  remove: (connectionId: string) => Promise<void>
  retry: () => void
  /** 进行中的连接 id；同一时间只允许一个连接被操作 */
  busyConnectionId: string | null
}

export type ModelConnectionsModel = ModelConnectionsData & ModelConnectionsActions

/**
 * BYOK 连接生命周期模块。
 *
 * 新建、验证、轮换、删除的编排集中在这里：成功后统一失效连接列表，
 * 创建与删除还会失效模型目录（模型出现/消失要立刻反映到对话模型选择器）。
 * 视图只负责三态切换与渲染，不再各自写 invalidate 与 toast。
 */
export function useModelConnections(): ModelConnectionsModel {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const catalogQuery = useQuery(modelCatalogQueryOptions)
  const connectionsQuery = useQuery(modelConnectionsQueryOptions)
  const providersQuery = useQuery(modelProvidersQueryOptions)

  const invalidateConnections = (): Promise<void> =>
    queryClient.invalidateQueries({ queryKey: queryKeys.models.connections })

  const invalidateCatalog = (): Promise<void> =>
    queryClient.invalidateQueries({ queryKey: queryKeys.models.catalog })

  const verifyMutation = useMutation({
    mutationFn: verifyModelConnection,
    onSuccess: async () => {
      // 凭证状态变化会改变 BYOK 模型在目录中的可见性，必须同时刷新对话模型选择器
      await Promise.all([invalidateConnections(), invalidateCatalog()])
      toast.success(t('settings.model.verifySuccess'))
    },
    // 验证失败时后端会把凭证标记为 INVALID；不刷新列表会让「已验证」标签停留在旧状态
    onError: async () => {
      await Promise.all([invalidateConnections(), invalidateCatalog()])
    },
  })

  const removeMutation = useMutation({
    mutationFn: deleteModelConnection,
    onSuccess: async () => {
      await Promise.all([invalidateConnections(), invalidateCatalog()])
      toast.success(t('settings.model.deleteSuccess'))
    },
  })

  const rotateMutation = useMutation({
    mutationFn: ({
      connectionId,
      payload,
    }: {
      connectionId: string
      payload: ModelConnectionUpdatePayload
    }) => updateModelConnection(connectionId, payload),
    onSuccess: async () => {
      // 轮换密钥同样可能让原本失效的模型重新可用
      await Promise.all([invalidateConnections(), invalidateCatalog()])
      toast.success(t('settings.model.rotateSuccess'))
    },
  })

  const catalog = catalogQuery.data?.list ?? []
  const connections = connectionsQuery.data?.list ?? []
  const providers = providersQuery.data ?? []

  const modelCounts = new Map<string, number>(
    providers.map((item) => [item.code, item.modelCount]),
  )
  const configuredProviderCodes = new Set(connections.map((connection) => connection.provider))

  const queryErrors = [catalogQuery.error, connectionsQuery.error, providersQuery.error].filter(
    (error): error is Error => Boolean(error),
  )
  const isUnavailable = queryErrors.length > 0 && queryErrors.every(isFeatureDisabledError)
  const isLoadError = queryErrors.length > 0 && !isUnavailable
  const isLoading = catalogQuery.isLoading || connectionsQuery.isLoading || providersQuery.isLoading

  const busyConnectionId = verifyMutation.isPending
    ? verifyMutation.variables
    : removeMutation.isPending
      ? removeMutation.variables
      : rotateMutation.isPending
        ? rotateMutation.variables?.connectionId
        : null

  const verify = async (connectionId: string): Promise<void> => {
    await verifyMutation.mutateAsync(connectionId)
  }

  const rotate = async (
    connectionId: string,
    payload: ModelConnectionUpdatePayload,
  ): Promise<void> => {
    // 失败时把 ApiError 抛回详情弹窗内联展示，避免全局提示打断表单输入
    await rotateMutation.mutateAsync({ connectionId, payload })
  }

  const remove = async (connectionId: string): Promise<void> => {
    await removeMutation.mutateAsync(connectionId)
  }

  const retry = (): void => {
    void catalogQuery.refetch()
    void connectionsQuery.refetch()
    void providersQuery.refetch()
  }

  return {
    catalog,
    connections,
    providers,
    providerCodes: providers.map((item) => item.code),
    modelCounts,
    configuredProviderCodes,
    isLoading,
    isUnavailable,
    isLoadError,
    busyConnectionId,
    verify,
    rotate,
    remove,
    retry,
  }
}

export interface ModelConnectionCreateApi {
  /** 成功后失效连接与模型目录并提示；失败把 ApiError 抛回表单做字段映射 */
  create: (payload: ModelConnectionCreatePayload) => Promise<ModelConnection>
  isCreating: boolean
}

/**
 * 新建连接模块。
 *
 * 与详情操作拆开的理由：接入表单只需要创建，不应为了一个动作去订阅三份查询；
 * 两者共用同一套失效与提示规则。
 */
export function useModelConnectionCreate(): ModelConnectionCreateApi {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const createMutation = useMutation({
    mutationFn: createModelConnection,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.models.connections }),
        queryClient.invalidateQueries({ queryKey: queryKeys.models.catalog }),
      ])
      toast.success(t('settings.model.addSuccess'))
    },
  })

  return {
    create: (payload) => createMutation.mutateAsync(payload),
    isCreating: createMutation.isPending,
  }
}
