import { useTranslation } from 'react-i18next'
import { ChevronRight, Plus } from 'lucide-react'

import type { ModelConnection } from '@/features/models/api'
import { Button } from '@/shared/ui/button'

import { ModelConnectionStatus } from './model-connection-status'
import { ModelProviderLogo } from './model-provider-logo'

export interface ModelProviderListProps {
  connections: readonly ModelConnection[]
  /** 点击任一已接入供应商进入详情 */
  onOpen: (connection: ModelConnection) => void
  onAdd: () => void
}

/** 默认视图：已接入供应商的行列表；整块面板 + 分隔线，避免卡片堆叠带来视觉噪声 */
export function ModelProviderList({ connections, onOpen, onAdd }: ModelProviderListProps) {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="text-sm font-medium text-foreground">
            {t('settings.model.overview.title')}
          </h3>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            {t('settings.model.overview.hint')}
          </p>
        </div>
        {connections.length > 0 ? (
          <Button type="button" size="sm" onClick={onAdd}>
            <Plus aria-hidden="true" />
            {t('settings.model.addProvider')}
          </Button>
        ) : null}
      </div>

      {connections.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-[var(--cds-panel-radius)] border border-dashed border-border px-6 py-10 text-center">
          <span className="flex size-12 items-center justify-center rounded-full border border-dashed border-border text-muted-foreground">
            <Plus className="size-5" aria-hidden="true" />
          </span>
          <div>
            <p className="text-sm font-medium text-foreground">{t('settings.model.emptyTitle')}</p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {t('settings.model.emptyHint')}
            </p>
          </div>
          <Button type="button" size="sm" onClick={onAdd}>
            {t('settings.model.addProvider')}
          </Button>
        </div>
      ) : null}

      {connections.length > 0 ? (
        <div className="overflow-hidden rounded-[var(--cds-panel-radius)] border border-border bg-surface">
          {connections.map((connection) => (
            <button
              key={connection.id}
              type="button"
              className="flex w-full items-center gap-3 border-b border-border px-4 py-3 text-left transition-colors last:border-b-0 hover:bg-muted/40 focus-visible:bg-muted/50 focus-visible:outline-none"
              onClick={() => onOpen(connection)}
            >
              <ModelProviderLogo
                providerCode={connection.provider}
                label={connection.providerName}
              />

              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="truncate text-sm font-medium text-foreground">
                    {connection.providerName}
                  </span>
                  <ModelConnectionStatus connection={connection} />
                </span>
                <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                  {connection.baseUrl || t('settings.model.detail.baseUrlDefault')}
                  {connection.credential ? ` · ${connection.credential.maskedHint}` : ''}
                </span>
              </span>

              <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}
