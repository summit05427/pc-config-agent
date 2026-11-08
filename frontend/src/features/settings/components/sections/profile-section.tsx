import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'

import { profileQueryOptions } from '@/features/settings/api'
import { Button } from '@/shared/ui/button'
import { Skeleton } from '@/shared/ui/skeleton'

import { ProfileForm } from '../profile-form'
import { SettingsSection } from '../settings-section'

function ProfileSkeleton() {
  return (
    <div className="flex flex-col gap-5" data-testid="profile-skeleton">
      <div className="flex items-center gap-4">
        <Skeleton className="size-10 rounded-full" />
        <div className="flex flex-1 flex-col gap-2">
          <Skeleton className="h-3.5 w-32" />
          <Skeleton className="h-3 w-56" />
        </div>
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
      </div>
      <Skeleton className="h-20 w-full" />
    </div>
  )
}

/** 个人资料：资料来自服务端缓存，只保留可编辑的资料表单 */
export function ProfileSection() {
  const { t } = useTranslation()
  const profileQuery = useQuery(profileQueryOptions)

  return (
    <SettingsSection
      title={t('settings.sections.profile')}
      description={t('settings.sectionHints.profile')}
    >
      {profileQuery.isLoading ? <ProfileSkeleton /> : null}

      {profileQuery.isError ? (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-3 rounded-[var(--cds-panel-radius)] border border-dashed border-border px-4 py-6"
        >
          <p className="min-w-0 flex-1 text-xs leading-relaxed text-muted-foreground">
            {t('settings.profile.saveFailed')}
          </p>
          <Button variant="outline" size="sm" onClick={() => void profileQuery.refetch()}>
            {t('common.retry')}
          </Button>
        </div>
      ) : null}

      {profileQuery.data ? <ProfileForm profile={profileQuery.data} /> : null}
    </SettingsSection>
  )
}
