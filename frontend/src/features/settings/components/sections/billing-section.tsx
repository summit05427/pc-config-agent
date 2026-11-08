import { useTranslation } from 'react-i18next'
import { CreditCard } from 'lucide-react'

import { Button } from '@/shared/ui/button'

import { SettingsSection } from '../settings-section'

/** 账单：订阅与发票能力尚未接入，先保留入口并明确标注不可用 */
export function BillingSection() {
  const { t } = useTranslation()

  return (
    <SettingsSection
      title={t('settings.sections.billing')}
      description={t('settings.sectionHints.billing')}
    >
      <div>
        <div className="flex flex-wrap items-center gap-3 rounded-[var(--cds-panel-radius)] border border-dashed border-border px-4 py-3">
          <CreditCard className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <p className="min-w-0 flex-1 text-xs text-muted-foreground">
            {t('settings.billing.empty')}
          </p>
          <Button variant="outline" size="sm" disabled>
            {t('settings.billing.manage')}
          </Button>
        </div>

        <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
          {t('settings.billing.hint')}
        </p>
      </div>
    </SettingsSection>
  )
}
