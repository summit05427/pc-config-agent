import { useTranslation } from 'react-i18next'

import { useAppStore } from '@/app/stores/app-store'
import type { AppLocale } from '@/shared/types/app'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/shared/ui/select'

import { useSettingsDraftStore } from '../../model/settings-draft'
import { SettingsField } from '../settings-field'
import { SettingsSection } from '../settings-section'
import { SettingsToggleRow } from '../settings-toggle-row'

const TIMEZONE_OPTIONS = [
  { value: 'Asia/Shanghai', label: 'Asia/Shanghai (UTC+8)' },
  { value: 'UTC', label: 'UTC' },
  { value: 'Europe/London', label: 'Europe/London (UTC+0)' },
  { value: 'America/New_York', label: 'America/New_York (UTC-5)' },
] as const

const TRIGGER_CLASS = 'w-full'

/** 常规设置：语言与时间开关写入 app-store，时区暂存本地草稿 */
export function GeneralSection() {
  const { t } = useTranslation()
  const locale = useAppStore((state) => state.locale)
  const setLocale = useAppStore((state) => state.setLocale)
  const showTimestamps = useAppStore((state) => state.showTimestamps)
  const setShowTimestamps = useAppStore((state) => state.setShowTimestamps)
  const general = useSettingsDraftStore((state) => state.general)
  const updateGeneral = useSettingsDraftStore((state) => state.updateGeneral)

  return (
    <SettingsSection
      title={t('settings.sections.general')}
      description={t('settings.sectionHints.general')}
    >
      <div className="grid gap-5 sm:grid-cols-2">
        <SettingsField
          id="settings-general-language"
          label={t('settings.general.language')}
          hint={t('settings.general.languageHint')}
        >
          <Select value={locale} onValueChange={(value) => setLocale(value as AppLocale)}>
            <SelectTrigger id="settings-general-language" size="sm" className={TRIGGER_CLASS}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent position="popper">
              <SelectItem value="zh-CN">{t('locale.zhCN')}</SelectItem>
              <SelectItem value="en-US">{t('locale.enUS')}</SelectItem>
            </SelectContent>
          </Select>
        </SettingsField>

        <SettingsField
          id="settings-general-timezone"
          label={t('settings.general.timezone')}
          hint={t('settings.general.timezoneHint')}
        >
          <Select
            value={general.timezone}
            onValueChange={(timezone) => updateGeneral({ timezone })}
          >
            <SelectTrigger id="settings-general-timezone" size="sm" className={TRIGGER_CLASS}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent position="popper">
              {TIMEZONE_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </SettingsField>
      </div>

      <div className="border-t border-border pt-6">
        <SettingsToggleRow
          id="settings-general-timestamps"
          label={t('settings.general.showTimestamps')}
          description={t('settings.general.showTimestampsHint')}
          checked={showTimestamps}
          onCheckedChange={setShowTimestamps}
        />
      </div>
    </SettingsSection>
  )
}
