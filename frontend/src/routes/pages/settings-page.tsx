import type { ComponentType } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from '@tanstack/react-router'

import { AgentSection } from '@/features/settings/components/sections/agent-section'
import { AppearanceSection } from '@/features/settings/components/sections/appearance-section'
import { ArchivedChatsSection } from '@/features/settings/components/sections/archived-chats-section'
import { BillingSection } from '@/features/settings/components/sections/billing-section'
import { ChatsSection } from '@/features/settings/components/sections/chats-section'
import { GeneralSection } from '@/features/settings/components/sections/general-section'
import { ModelSection } from '@/features/settings/components/sections/model-section'
import { ProfileSection } from '@/features/settings/components/sections/profile-section'
import { SecuritySection } from '@/features/settings/components/sections/security-section'
import { StorageSection } from '@/features/settings/components/sections/storage-section'
import { UsageSection } from '@/features/settings/components/sections/usage-section'
import {
  resolveSettingsSection,
  type SettingsSectionId,
} from '@/features/settings/model/settings-sections'

const SECTION_COMPONENTS: Record<SettingsSectionId, ComponentType> = {
  profile: ProfileSection,
  security: SecuritySection,
  chats: ChatsSection,
  'archived-chats': ArchivedChatsSection,
  storage: StorageSection,
  billing: BillingSection,
  general: GeneralSection,
  appearance: AppearanceSection,
  model: ModelSection,
  usage: UsageSection,
  agent: AgentSection,
}

/**
 * 设置页。
 *
 * 分区目录由侧栏与移动抽屉承担，内容区只渲染当前分类，避免出现第二份目录；
 * 分区只由 URL 决定，非法或缺失时再兜底解析一次，保证刷新与直达时内容一致。
 */
export function SettingsPage() {
  const { t } = useTranslation()
  const params = useParams({ strict: false })
  const activeSection = resolveSettingsSection(params.section)
  const ActiveSection = SECTION_COMPONENTS[activeSection]

  // 与对话区一致：始终预留滚动条槽位，分区内容变高时不会因滚动条占宽而整体左移；
  // both-edges 让预留左右对称，居中内容的中轴保持不动
  return (
    <div className="h-full overflow-y-auto [scrollbar-gutter:stable_both-edges]">
      <div className="mx-auto w-full max-w-[var(--app-content-width)] px-4 pt-12 pb-8 sm:px-8 sm:py-10">
        <h1 className="sr-only">{t('settings.title')}</h1>

        <ActiveSection />
      </div>
    </div>
  )
}
