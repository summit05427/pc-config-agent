import {
  Archive,
  ChartColumn,
  CreditCard,
  HardDrive,
  KeyRound,
  MessageSquare,
  Palette,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  UserRound,
  type LucideIcon,
} from 'lucide-react'

/** 设置分区 id 与路由参数一一对应，新增分区必须同步导航与 i18n 词条 */
export type SettingsSectionId =
  | 'profile'
  | 'security'
  | 'chats'
  | 'archived-chats'
  | 'storage'
  | 'billing'
  | 'general'
  | 'appearance'
  | 'model'
  | 'usage'
  | 'agent'

export interface SettingsSectionMeta {
  id: SettingsSectionId
  titleKey: string
  icon: LucideIcon
}

export interface SettingsGroupMeta {
  id: 'account' | 'preferences'
  titleKey: string
  sections: SettingsSectionMeta[]
}

export const DEFAULT_SETTINGS_SECTION: SettingsSectionId = 'general'

/** 分组顺序即导航顺序：账户在上，偏好设置在下 */
export const SETTINGS_GROUPS: readonly SettingsGroupMeta[] = [
  {
    id: 'account',
    titleKey: 'settings.groups.account',
    sections: [
      { id: 'profile', titleKey: 'settings.sections.profile', icon: UserRound },
      { id: 'security', titleKey: 'settings.sections.security', icon: ShieldCheck },
      { id: 'chats', titleKey: 'settings.sections.chats', icon: MessageSquare },
      { id: 'archived-chats', titleKey: 'settings.sections.archivedChats', icon: Archive },
      { id: 'storage', titleKey: 'settings.sections.storage', icon: HardDrive },
      { id: 'billing', titleKey: 'settings.sections.billing', icon: CreditCard },
      { id: 'model', titleKey: 'settings.sections.model', icon: KeyRound },
      { id: 'usage', titleKey: 'settings.sections.usage', icon: ChartColumn },
    ],
  },
  {
    id: 'preferences',
    titleKey: 'settings.groups.preferences',
    sections: [
      { id: 'general', titleKey: 'settings.sections.general', icon: SlidersHorizontal },
      { id: 'appearance', titleKey: 'settings.sections.appearance', icon: Palette },
      { id: 'agent', titleKey: 'settings.sections.agent', icon: Sparkles },
    ],
  },
]

export const SETTINGS_SECTIONS: readonly SettingsSectionMeta[] = SETTINGS_GROUPS.flatMap(
  (group) => group.sections,
)

export const isSettingsSectionId = (value: unknown): value is SettingsSectionId =>
  SETTINGS_SECTIONS.some((section) => section.id === value)

/**
 * 把路由参数收敛成合法分区。
 *
 * `/settings` 与非法分区统一回落到默认分区，导航与内容区共用同一份判定，
 * 避免出现「导航高亮常规、内容区却留空」的状态。
 */
export const resolveSettingsSection = (value: unknown): SettingsSectionId => {
  const raw = Array.isArray(value) ? value[0] : value
  return isSettingsSectionId(raw) ? raw : DEFAULT_SETTINGS_SECTION
}
