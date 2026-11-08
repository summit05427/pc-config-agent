import { useTranslation } from 'react-i18next'

import { ModelUsagePanel } from '../model-usage-panel'
import { SettingsSection } from '../settings-section'
import { UsageOverview } from '../usage-overview'

/** 使用统计分区：上部为应用用量概览，下部为模型调用明细 */
export function UsageSection() {
  const { t } = useTranslation()

  return (
    <SettingsSection
      title={t('settings.sections.usage')}
      description={t('settings.sectionHints.usage')}
    >
      <UsageOverview />
      <ModelUsagePanel />
    </SettingsSection>
  )
}
