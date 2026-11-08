import { useTranslation } from 'react-i18next'
import { Link } from '@tanstack/react-router'
import { ArrowLeft } from 'lucide-react'

import { ROUTE_PATHS } from '@/routes/paths'
import { cn } from '@/shared/lib/utils'

import {
  SETTINGS_GROUPS,
  type SettingsSectionId,
} from '../model/settings-sections'

export interface SettingsNavProps {
  activeSection: SettingsSectionId
  /** 折叠态退化为图标 rail，与主侧栏的折叠表现保持一致 */
  collapsed?: boolean
  /** 移动抽屉点选后需要立即收起，桌面侧栏不传 */
  onNavigate?: () => void
}

const ROW_CLASS =
  'mb-0.5 flex h-[var(--app-sidebar-row-height)] items-center gap-2 rounded-[var(--cds-radius-btn-xs)] px-2 text-nav transition-colors'
const COLLAPSED_ROW_CLASS = 'justify-center px-0'
const IDLE_CLASS =
  'text-sidebar-foreground/85 hover:bg-sidebar-accent/70 hover:text-sidebar-accent-foreground'
const ACTIVE_CLASS = 'bg-sidebar-accent font-medium text-sidebar-accent-foreground'

/** 设置分区导航：返回工作区 + 两个分组，当前分区用 aria-current 标记；折叠时只留图标 */
export function SettingsNav({
  activeSection,
  collapsed = false,
  onNavigate,
}: SettingsNavProps) {
  const { t } = useTranslation()

  const resolveRowClass = (isActive: boolean): string =>
    cn(ROW_CLASS, isActive ? ACTIVE_CLASS : IDLE_CLASS, collapsed && COLLAPSED_ROW_CLASS)

  const renderLabel = (label: string) =>
    collapsed ? <span className="sr-only">{label}</span> : <span className="truncate">{label}</span>

  return (
    <nav className="flex min-h-0 flex-1 flex-col" aria-label={t('settings.navLabel')}>
      <div className="shrink-0 px-2 pb-1">
        <Link
          to={ROUTE_PATHS.chatNew}
          title={collapsed ? t('settings.backToWorkspace') : undefined}
          onClick={onNavigate}
          className={resolveRowClass(false)}
        >
          <ArrowLeft className="size-4 shrink-0" aria-hidden="true" />
          {renderLabel(t('settings.backToWorkspace'))}
        </Link>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        {SETTINGS_GROUPS.map((group, index) => (
          <div key={group.id} className={index === 0 ? undefined : 'mt-6'}>
            {collapsed ? null : (
              <p className="px-2 pb-1.5 text-xs font-medium tracking-wide text-muted-foreground">
                {t(group.titleKey)}
              </p>
            )}

            {group.sections.map((section) => (
              <Link
                key={section.id}
                to="/settings/$section"
                params={{ section: section.id }}
                aria-current={activeSection === section.id ? 'page' : undefined}
                title={collapsed ? t(section.titleKey) : undefined}
                onClick={onNavigate}
                className={resolveRowClass(activeSection === section.id)}
              >
                <section.icon className="size-4 shrink-0" aria-hidden="true" />
                {renderLabel(t(section.titleKey))}
              </Link>
            ))}
          </div>
        ))}
      </div>
    </nav>
  )
}
