import type { ReactNode } from 'react'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import {
  DEFAULT_SETTINGS_SECTION,
  isSettingsSectionId,
  resolveSettingsSection,
} from '../model/settings-sections'
import { SettingsNav } from './settings-nav'

interface MockLinkProps {
  children?: ReactNode
  className?: string
  'aria-current'?: 'page'
}

// 导航只关心高亮结果，替换掉依赖 RouterContext 的 Link 即可单独验证
vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, className, 'aria-current': ariaCurrent }: MockLinkProps) => (
    <a href="#" className={className} aria-current={ariaCurrent}>
      {children}
    </a>
  ),
}))

describe('settings section resolver', () => {
  it('非法分区回落到默认分区', () => {
    expect(resolveSettingsSection('not-a-section')).toBe(DEFAULT_SETTINGS_SECTION)
    expect(resolveSettingsSection(undefined)).toBe(DEFAULT_SETTINGS_SECTION)
    expect(resolveSettingsSection(['unknown'])).toBe(DEFAULT_SETTINGS_SECTION)
  })

  it('合法分区原样返回并可通过类型守卫识别', () => {
    expect(resolveSettingsSection('profile')).toBe('profile')
    expect(isSettingsSectionId('profile')).toBe(true)
    expect(isSettingsSectionId('unknown')).toBe(false)
  })
})

describe('SettingsNav', () => {
  it('非法分区解析后仍高亮默认分区，内容与导航不会错位', () => {
    const activeSection = resolveSettingsSection('not-a-section')

    render(<SettingsNav activeSection={activeSection} />)

    expect(screen.getByRole('link', { name: /常规/ })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: /个人资料/ })).not.toHaveAttribute('aria-current')
  })

  it('账户组提供已归档的聊天、存储与账单入口', () => {
    render(<SettingsNav activeSection="profile" />)

    expect(screen.getByRole('link', { name: '已归档的聊天' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '存储' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '账单' })).toBeInTheDocument()
  })

  it('账户组提供使用统计入口', () => {
    render(<SettingsNav activeSection="profile" />)

    expect(screen.getByRole('link', { name: '使用统计' })).toBeInTheDocument()
  })
})
