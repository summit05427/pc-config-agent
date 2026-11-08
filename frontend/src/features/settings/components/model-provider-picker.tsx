import { useTranslation } from 'react-i18next'
import { ChevronRight } from 'lucide-react'

import { Badge } from '@/shared/ui/badge'

import { getProviderMeta } from '../model/provider-meta'
import { ModelProviderLogo } from './model-provider-logo'
import { ModelViewHeader } from './model-view-header'

export interface ModelProviderPickerProps {
  providers: readonly string[]
  configuredProviderCodes: ReadonlySet<string>
  /** provider code → 目录中的模型数量，用于卡片副标题 */
  modelCounts: ReadonlyMap<string, number>
  onSelect: (providerCode: string) => void
  onBack: () => void
}

/** 添加供应商：按品牌展示可接入 Provider，已接入项禁用并标注状态 */
export function ModelProviderPicker({
  providers,
  configuredProviderCodes,
  modelCounts,
  onSelect,
  onBack,
}: ModelProviderPickerProps) {
  const { t } = useTranslation()

  const sortedProviders = [...providers].sort((left, right) =>
    getProviderMeta(left).name.localeCompare(getProviderMeta(right).name, 'en'),
  )

  return (
    <div className="flex flex-col gap-6">
      <ModelViewHeader
        backLabel={t('settings.model.back')}
        title={t('settings.model.picker.title')}
        description={t('settings.model.picker.description')}
        onBack={onBack}
      />

      {sortedProviders.length === 0 ? (
        <p className="rounded-[var(--cds-panel-radius)] border border-dashed border-border px-4 py-10 text-center text-xs text-muted-foreground">
          {t('settings.model.picker.empty')}
        </p>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {sortedProviders.map((providerCode) => {
            const meta = getProviderMeta(providerCode)
            const isConfigured = configuredProviderCodes.has(providerCode)
            const modelCount = modelCounts.get(providerCode) ?? 0

            return (
              <button
                key={providerCode}
                type="button"
                disabled={isConfigured}
                className="group flex items-center gap-3 rounded-[var(--cds-panel-radius)] border border-border bg-surface px-3 py-3 text-left transition-colors hover:border-foreground/25 hover:bg-muted/40 focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/35 disabled:cursor-default disabled:opacity-60 disabled:hover:border-border disabled:hover:bg-surface"
                onClick={() => onSelect(providerCode)}
              >
                <ModelProviderLogo providerCode={providerCode} label={meta.name} />

                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-foreground">
                    {meta.name}
                  </span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    {modelCount > 0
                      ? t('settings.model.picker.modelsCount', { count: modelCount })
                      : t('settings.model.picker.noModels')}
                  </span>
                </span>

                {isConfigured ? (
                  <Badge
                    variant="outline"
                    className="border-success/40 bg-success/10 text-success"
                  >
                    {t('settings.model.picker.connected')}
                  </Badge>
                ) : (
                  <ChevronRight
                    className="size-4 shrink-0 text-muted-foreground"
                    aria-hidden="true"
                  />
                )}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
