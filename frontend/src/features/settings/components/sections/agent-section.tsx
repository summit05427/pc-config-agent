import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'

import { preferencesQueryOptions } from '@/features/settings/api'
import { Button } from '@/shared/ui/button'
import { Skeleton } from '@/shared/ui/skeleton'

import { AgentForm } from '../agent-form'
import { SettingsSection } from '../settings-section'

/** 个性化：读取服务端偏好后挂载表单，避免用 effect 回填默认值 */
export function AgentSection() {
  const { t } = useTranslation()
  const preferencesQuery = useQuery(preferencesQueryOptions)

  return (
    <SettingsSection
      title={t('settings.sections.agent')}
      description={t('settings.sectionHints.agent')}
    >
      {preferencesQuery.isLoading ? (
        <div className="flex flex-col gap-5" data-testid="agent-skeleton">
          <Skeleton className="h-24 w-full" />
          <div className="grid gap-5 sm:grid-cols-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        </div>
      ) : null}

      {preferencesQuery.isError ? (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-3 rounded-[var(--cds-panel-radius)] border border-dashed border-border px-4 py-6"
        >
          <p className="min-w-0 flex-1 text-xs leading-relaxed text-muted-foreground">
            {t('settings.agent.saveFailed')}
          </p>
          <Button variant="outline" size="sm" onClick={() => void preferencesQuery.refetch()}>
            {t('common.retry')}
          </Button>
        </div>
      ) : null}

      {preferencesQuery.data ? <AgentForm preferences={preferencesQuery.data} /> : null}
    </SettingsSection>
  )
}
