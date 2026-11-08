import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { ModelConnection, ModelConnectionUpdatePayload } from '@/features/models/api'
import { Button } from '@/shared/ui/button'
import { Skeleton } from '@/shared/ui/skeleton'

import { ModelConnectionDetail } from '../model-connection-detail'
import { useModelConnections } from '../../model/use-model-connections'
import { ModelProviderConnect } from '../model-provider-connect'
import { ModelProviderList } from '../model-provider-list'
import { ModelProviderPicker } from '../model-provider-picker'
import { SettingsSection } from '../settings-section'

/** 分区内三态钻取：列表 → 选择供应商 → 详情；详情含已接入与待接入两种子态 */
type ModelSectionView =
  | { mode: 'list' }
  | { mode: 'picker' }
  | { mode: 'connect'; providerCode: string }
  | { mode: 'detail'; connectionId: string }

const INITIAL_VIEW: ModelSectionView = { mode: 'list' }

/**
 * 模型与密钥分区。
 *
 * 生命周期操作（验证、轮换、删除）由 useModelConnections 统一编排：
 * 缓存失效与成功提示都在模块内完成，这里只负责三态钻取与在失败时保持当前视图。
 * 三个子视图只切换渲染，不改变 URL：设置页的权威状态仍是分类参数。
 */
export function ModelSection() {
  const { t } = useTranslation()
  const [view, setView] = useState<ModelSectionView>(INITIAL_VIEW)
  const model = useModelConnections()

  const connections = model.connections
  const selectedConnection =
    view.mode === 'detail'
      ? connections.find((connection) => connection.id === view.connectionId)
      : undefined

  const verify = async (connection: ModelConnection): Promise<void> => {
    try {
      await model.verify(connection.id)
    } catch {
      // 请求层已提示服务端错误，这里保持详情不变
    }
  }

  const remove = async (connection: ModelConnection): Promise<void> => {
    try {
      await model.remove(connection.id)
      setView(INITIAL_VIEW)
    } catch {
      // 请求层已提示服务端错误，这里保持详情不变
    }
  }

  const rotate = (
    connection: ModelConnection,
    payload: ModelConnectionUpdatePayload,
  ): Promise<void> => model.rotate(connection.id, payload)

  const showList = view.mode === 'list' || (view.mode === 'detail' && !selectedConnection)

  let content: ReactNode = null
  if (model.isUnavailable) {
    content = (
      <p className="text-sm leading-relaxed text-muted-foreground">
        {t('settings.model.unavailable')}
      </p>
    )
  } else if (model.isLoading) {
    content = (
      <div className="flex flex-col gap-4" data-testid="model-skeleton">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    )
  } else if (model.isLoadError) {
    content = (
      <div className="flex flex-col items-start gap-3">
        <p className="text-sm leading-relaxed text-muted-foreground">
          {t('settings.model.loadFailed')}
        </p>
        <Button type="button" variant="outline" size="sm" onClick={model.retry}>
          {t('settings.model.retry')}
        </Button>
      </div>
    )
  } else if (showList) {
    content = (
      <ModelProviderList
        connections={connections}
        onOpen={(connection) => setView({ mode: 'detail', connectionId: connection.id })}
        onAdd={() => setView({ mode: 'picker' })}
      />
    )
  } else if (view.mode === 'picker') {
    content = (
      <ModelProviderPicker
        providers={model.providerCodes}
        configuredProviderCodes={model.configuredProviderCodes}
        modelCounts={model.modelCounts}
        onSelect={(providerCode) => setView({ mode: 'connect', providerCode })}
        onBack={() => setView(INITIAL_VIEW)}
      />
    )
  } else if (view.mode === 'connect') {
    content = (
      <ModelProviderConnect
        providerCode={view.providerCode}
        models={model.catalog.filter((item) => item.provider === view.providerCode)}
        onBack={() => setView({ mode: 'picker' })}
        onCreated={(connection) => setView({ mode: 'detail', connectionId: connection.id })}
      />
    )
  } else if (view.mode === 'detail' && selectedConnection) {
    content = (
      <ModelConnectionDetail
        connection={selectedConnection}
        models={model.catalog.filter((item) => item.provider === selectedConnection.provider)}
        isBusy={model.busyConnectionId === selectedConnection.id}
        onBack={() => setView(INITIAL_VIEW)}
        onVerify={() => void verify(selectedConnection)}
        onRotate={(payload) => rotate(selectedConnection, payload)}
        onDelete={() => void remove(selectedConnection)}
      />
    )
  }

  return (
    <SettingsSection
      title={t('settings.sections.model')}
      description={t('settings.sectionHints.model')}
    >
      {content}
    </SettingsSection>
  )
}
