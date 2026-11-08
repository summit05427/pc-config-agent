import { useTranslation } from 'react-i18next'
import { useNavigate } from '@tanstack/react-router'

import { useAuthSessionStore } from '@/features/auth/model/auth-session'
import { ROUTE_PATHS } from '@/routes/paths'
import { Button } from '@/shared/ui/button'

import { DeviceSessions } from '../device-sessions'
import { SettingsSection } from '../settings-section'

/** 账户安全：设备会话与危险区 */
export function SecuritySection() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const logout = useAuthSessionStore((state) => state.logout)

  const signOut = async (): Promise<void> => {
    await logout()
    await navigate({ to: ROUTE_PATHS.login, replace: true })
  }

  return (
    <SettingsSection
      title={t('settings.sections.security')}
      description={t('settings.sectionHints.security')}
    >
      <DeviceSessions />

      <div className="flex flex-col gap-4 border-t border-border pt-6">
        <div>
          <h3 className="text-sm font-medium text-destructive">
            {t('settings.security.dangerTitle')}
          </h3>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            {t('settings.security.signOutHint')}
          </p>
        </div>
        <div>
          <Button variant="destructive" size="sm" onClick={() => void signOut()}>
            {t('settings.security.signOut')}
          </Button>
        </div>
      </div>
    </SettingsSection>
  )
}
