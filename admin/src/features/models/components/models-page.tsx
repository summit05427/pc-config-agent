import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { getHttpErrorMessage } from '@/core/http/errors'
import { toast } from 'sonner'
import { queryKeys } from '@/lib/query-keys'
import { Card, CardContent } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { PaginationBar } from '@/components/pagination-bar'
import {
  adminModelsQueryOptions,
  adminProvidersQueryOptions,
  updateModelStatus,
  updateProviderStatus,
} from '../api/admin-models-api'
import type {
  AdminModelSummary,
  AdminProviderSummary,
  ModelEnabledFilter,
} from '../types'
import { ModelPricingDialog } from './model-pricing-dialog'
import { ModelsFilters } from './models-filters'
import { ModelsTable } from './models-table'
import { ProvidersBar } from './providers-bar'

export function ModelsPage() {
  const search = useSearch({ from: '/_authenticated/models/' })
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [pricingModel, setPricingModel] = useState<AdminModelSummary | null>(
    null
  )
  const [pendingModel, setPendingModel] = useState<AdminModelSummary | null>(
    null
  )
  const [pendingProvider, setPendingProvider] =
    useState<AdminProviderSummary | null>(null)

  const providersQuery = useQuery(adminProvidersQueryOptions())
  const modelsQuery = useQuery(
    adminModelsQueryOptions({
      page: search.page,
      size: search.size,
      keyword: search.keyword || undefined,
      provider: search.provider || undefined,
      enabled: search.enabled || undefined,
    })
  )

  const modelStatusMutation = useMutation({
    mutationFn: (input: { model: AdminModelSummary; enabled: boolean }) =>
      updateModelStatus(
        input.model.provider,
        input.model.modelKey,
        input.enabled
      ),
    onSuccess: (model) => {
      toast.success(
        `${model.provider}:${model.modelKey} 已${model.enabled ? '启用' : '停用'}`
      )
      setPendingModel(null)
      void queryClient.invalidateQueries({
        queryKey: queryKeys.adminModels.all,
      })
    },
    onError: (error) => {
      toast.error(getHttpErrorMessage(error))
      setPendingModel(null)
    },
  })

  const providerStatusMutation = useMutation({
    mutationFn: (input: { provider: AdminProviderSummary; enabled: boolean }) =>
      updateProviderStatus(input.provider.code, input.enabled),
    onSuccess: (provider) => {
      toast.success(
        `${provider.displayName} 已${provider.enabled ? '启用' : '停用'}`
      )
      setPendingProvider(null)
      void queryClient.invalidateQueries({
        queryKey: queryKeys.modelProviders.all,
      })
      // Provider 状态会影响模型列表的可用性展示，一并刷新
      void queryClient.invalidateQueries({
        queryKey: queryKeys.adminModels.all,
      })
    },
    onError: (error) => {
      toast.error(getHttpErrorMessage(error))
      setPendingProvider(null)
    },
  })

  function updateSearch(next: {
    page?: number
    size?: number
    keyword?: string
    provider?: string
    enabled?: ModelEnabledFilter
  }) {
    navigate({
      to: '/models',
      search: (previous) => ({
        keyword: next.keyword ?? previous.keyword ?? '',
        provider: next.provider ?? previous.provider ?? '',
        enabled: (next.enabled ?? previous.enabled) as ModelEnabledFilter,
        size: next.size ?? previous.size ?? 20,
        // 过滤条件变化时回到第一页，避免停留在越界页码
        page: next.page ?? 1,
      }),
    })
  }

  function toggleModel(model: AdminModelSummary) {
    if (model.enabled) {
      setPendingModel(model)
      return
    }
    modelStatusMutation.mutate({ model, enabled: true })
  }

  function toggleProvider(provider: AdminProviderSummary) {
    if (provider.enabled) {
      setPendingProvider(provider)
      return
    }
    providerStatusMutation.mutate({ provider, enabled: true })
  }

  return (
    <>
      <Header fixed />
      <Main className='flex flex-1 flex-col gap-4 sm:gap-6'>
        <div className='flex flex-col gap-4'>
          <div>
            <h1 className='text-2xl font-bold tracking-tight'>模型与定价</h1>
            <p className='text-sm text-muted-foreground'>
              维护 Provider
              与模型启停，并按生效时间追加定价版本；停用只影响新调用解析。
            </p>
          </div>

          <Card>
            <CardContent>
              <ProvidersBar
                providers={providersQuery.data ?? []}
                isPending={providersQuery.isPending}
                hasError={providersQuery.isError}
                onToggle={toggleProvider}
              />
            </CardContent>
          </Card>

          <ModelsFilters
            keyword={search.keyword}
            provider={search.provider}
            enabled={search.enabled}
            size={search.size}
            providers={providersQuery.data ?? []}
            onKeywordChange={(keyword) => updateSearch({ keyword })}
            onProviderChange={(provider) => updateSearch({ provider })}
            onEnabledChange={(enabled) => updateSearch({ enabled })}
            onSizeChange={(size) => updateSearch({ size })}
          />

          <Card>
            <CardContent>
              <ModelsTable
                models={modelsQuery.data?.list ?? []}
                isPending={modelsQuery.isPending}
                hasError={modelsQuery.isError}
                isStatusUpdating={modelStatusMutation.isPending}
                onOpenPricing={setPricingModel}
                onToggleStatus={toggleModel}
                onRetry={() => void modelsQuery.refetch()}
              />
            </CardContent>
          </Card>

          <PaginationBar
            page={search.page}
            size={search.size}
            total={modelsQuery.data?.total ?? 0}
            isDisabled={modelsQuery.isPending}
            onPageChange={(page) => updateSearch({ page })}
          />

          {pricingModel && (
            <ModelPricingDialog
              // 换模型时重新挂载，表单默认值与版本列表都直接来自 props
              key={`${pricingModel.provider}:${pricingModel.modelKey}`}
              model={pricingModel}
              onOpenChange={(open) => {
                if (!open) setPricingModel(null)
              }}
            />
          )}

          <ConfirmDialog
            open={pendingModel !== null}
            onOpenChange={(open) => {
              if (!open) setPendingModel(null)
            }}
            title='停用模型'
            desc={
              pendingModel
                ? `停用后 ${pendingModel.provider}:${pendingModel.modelKey} 不再参与新调用解析，历史台账不受影响。`
                : ''
            }
            confirmText='停用'
            destructive
            isLoading={modelStatusMutation.isPending}
            handleConfirm={() => {
              if (pendingModel) {
                modelStatusMutation.mutate({
                  model: pendingModel,
                  enabled: false,
                })
              }
            }}
          />

          <ConfirmDialog
            open={pendingProvider !== null}
            onOpenChange={(open) => {
              if (!open) setPendingProvider(null)
            }}
            title='停用 Provider'
            desc={
              pendingProvider
                ? `停用后 ${pendingProvider.displayName} 下全部模型对新调用不可用，重新启用即可恢复。`
                : ''
            }
            confirmText='停用'
            destructive
            isLoading={providerStatusMutation.isPending}
            handleConfirm={() => {
              if (pendingProvider) {
                providerStatusMutation.mutate({
                  provider: pendingProvider,
                  enabled: false,
                })
              }
            }}
          />
        </div>
      </Main>
    </>
  )
}
