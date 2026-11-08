import { useTranslation } from 'react-i18next'

import type { ModelCatalogItem } from '@/features/models/api'
import { Badge } from '@/shared/ui/badge'

/** 平台目录已知能力的中文词条；未知能力保留原始标识，便于发现新增能力 */
const CAPABILITY_LABELS: Record<string, string> = {
  text: 'settings.model.detail.capabilityText',
  tool_calling: 'settings.model.detail.capabilityToolCalling',
  vision: 'settings.model.detail.capabilityVision',
}

const NUMBER_FORMAT = new Intl.NumberFormat('en-US')

export interface ModelCatalogListProps {
  models: readonly ModelCatalogItem[]
}

/** 可用模型只读列表：固定高度容器，超出滚动，避免长目录拉长整个设置分区 */
export function ModelCatalogList({ models }: ModelCatalogListProps) {
  const { t } = useTranslation()

  if (models.length === 0) {
    return (
      <p className="rounded-[var(--cds-panel-radius)] border border-dashed border-border px-4 py-6 text-center text-xs text-muted-foreground">
        {t('settings.model.detail.modelsEmpty')}
      </p>
    )
  }

  return (
    <div className="max-h-80 overflow-y-auto rounded-[var(--cds-panel-radius)] border border-border bg-surface">
      <ul className="divide-y divide-border">
        {models.map((model) => (
          <li
            key={model.modelKey}
            className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="min-w-0">
              <p className="truncate text-sm text-foreground">{model.displayName}</p>
              <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground">
                {model.modelKey}
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-1.5">
              {model.capabilities.map((capability) => {
                const labelKey = CAPABILITY_LABELS[capability]
                return (
                  <Badge key={capability} variant="outline">
                    {labelKey ? t(labelKey) : capability}
                  </Badge>
                )
              })}
              {model.contextWindow === null ? null : (
                <span className="tabular text-xs text-muted-foreground">
                  {t('settings.model.detail.contextWindow', {
                    tokens: NUMBER_FORMAT.format(model.contextWindow),
                  })}
                </span>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
