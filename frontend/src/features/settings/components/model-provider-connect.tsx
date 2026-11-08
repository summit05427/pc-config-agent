import { useTranslation } from 'react-i18next'

import type { ModelCatalogItem, ModelConnection } from '@/features/models/api'

import { getProviderMeta } from '../model/provider-meta'
import { ModelCatalogList } from './model-catalog-list'
import { ModelConnectionForm } from './model-connection-form'
import { ModelProviderLogo } from './model-provider-logo'
import { ModelViewHeader } from './model-view-header'

export interface ModelProviderConnectProps {
  providerCode: string
  /** 当前 Provider 在平台目录中的模型，仅作接入前的只读预览 */
  models: readonly ModelCatalogItem[]
  onBack: () => void
  onCreated: (connection: ModelConnection) => void
}

/** 未接入供应商：同一详情壳内展示接入表单与目录预览，成功后由父视图跳转到详情 */
export function ModelProviderConnect({
  providerCode,
  models,
  onBack,
  onCreated,
}: ModelProviderConnectProps) {
  const { t } = useTranslation()
  const meta = getProviderMeta(providerCode)

  return (
    <div className="flex flex-col gap-6">
      <ModelViewHeader
        backLabel={t('settings.model.back')}
        title={t('settings.model.connect.title', { provider: meta.name })}
        description={t('settings.model.connect.description')}
        onBack={onBack}
        leading={<ModelProviderLogo providerCode={providerCode} label={meta.name} size="md" />}
      />

      <div className="rounded-[var(--cds-panel-radius)] border border-border bg-surface px-4 py-5 sm:px-5">
        <ModelConnectionForm key={providerCode} providerCode={providerCode} onCreated={onCreated} />
      </div>

      <section className="flex flex-col gap-2">
        <h4 className="text-sm font-medium text-foreground">
          {t('settings.model.detail.modelsTitle')}
        </h4>
        <p className="text-xs leading-relaxed text-muted-foreground">
          {t('settings.model.detail.modelsHint')}
        </p>
        <ModelCatalogList models={models} />
      </section>
    </div>
  )
}
