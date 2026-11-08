import { useTranslation } from 'react-i18next'

import { useAppStore } from '@/app/stores/app-store'
import type { FontScale } from '@/shared/types/app'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/shared/ui/select'

import { SettingsField } from '../settings-field'
import { SettingsSection } from '../settings-section'
import { SettingsToggleRow } from '../settings-toggle-row'
import { ThemeModeSelector } from '../theme-mode-selector'

const FONT_SCALE_OPTIONS = [
  { value: 'small', labelKey: 'settings.appearance.fontScaleSmall' },
  { value: 'default', labelKey: 'settings.appearance.fontScaleDefault' },
  { value: 'large', labelKey: 'settings.appearance.fontScaleLarge' },
] as const

const TRIGGER_CLASS = 'w-full'

export function AppearanceSection() {
  const { t } = useTranslation()
  const fontScale = useAppStore((state) => state.fontScale)
  const setFontScale = useAppStore((state) => state.setFontScale)
  const showAccountMenuIcon = useAppStore((state) => state.showAccountMenuIcon)
  const setShowAccountMenuIcon = useAppStore((state) => state.setShowAccountMenuIcon)

  return (
    <SettingsSection
      title={t('settings.sections.appearance')}
      description={t('settings.sectionHints.appearance')}
    >
      <div className="flex flex-col gap-3">
        <div>
          <h3 className="text-sm font-medium text-foreground">{t('settings.appearance.theme')}</h3>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            {t('settings.appearance.themeHint')}
          </p>
        </div>

        <ThemeModeSelector />
      </div>

      <div className="grid gap-5 border-t border-border pt-6">
        <SettingsField id="settings-appearance-font" label={t('settings.appearance.fontScale')}>
          <Select
            value={fontScale}
            onValueChange={(value) => setFontScale(value as FontScale)}
          >
            <SelectTrigger id="settings-appearance-font" size="sm" className={TRIGGER_CLASS}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent position="popper">
              {FONT_SCALE_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {t(option.labelKey)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </SettingsField>
      </div>
      <div className="border-t border-border pt-6">
        <SettingsToggleRow
          id="settings-appearance-account-menu-icon"
          label={t('settings.appearance.accountMenuIcon')}
          description={t('settings.appearance.accountMenuIconHint')}
          checked={showAccountMenuIcon}
          onCheckedChange={setShowAccountMenuIcon}
        />
      </div>
    </SettingsSection>
  )
}
