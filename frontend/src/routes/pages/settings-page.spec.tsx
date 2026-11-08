import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  section: 'profile' as unknown,
}))

// 页面只依赖路由参数，目录已移交给侧栏与移动抽屉，这里不需要导航能力
vi.mock('@tanstack/react-router', () => ({
  useParams: () => ({ section: mocks.section }),
}))

// 分区内容各自依赖网络与表单，这里只验证设置页的编排逻辑
vi.mock('@/features/settings/components/sections/profile-section', () => ({
  ProfileSection: () => <p>profile-section</p>,
}))
vi.mock('@/features/settings/components/sections/security-section', () => ({
  SecuritySection: () => <p>security-section</p>,
}))
vi.mock('@/features/settings/components/sections/chats-section', () => ({
  ChatsSection: () => <p>chats-section</p>,
}))
vi.mock('@/features/settings/components/sections/archived-chats-section', () => ({
  ArchivedChatsSection: () => <p>archived-chats-section</p>,
}))
vi.mock('@/features/settings/components/sections/storage-section', () => ({
  StorageSection: () => <p>storage-section</p>,
}))
vi.mock('@/features/settings/components/sections/billing-section', () => ({
  BillingSection: () => <p>billing-section</p>,
}))
vi.mock('@/features/settings/components/sections/general-section', () => ({
  GeneralSection: () => <p>general-section</p>,
}))
vi.mock('@/features/settings/components/sections/appearance-section', () => ({
  AppearanceSection: () => <p>appearance-section</p>,
}))
vi.mock('@/features/settings/components/sections/model-section', () => ({
  ModelSection: () => <p>model-section</p>,
}))
vi.mock('@/features/settings/components/sections/usage-section', () => ({
  UsageSection: () => <p>usage-section</p>,
}))
vi.mock('@/features/settings/components/sections/agent-section', () => ({
  AgentSection: () => <p>agent-section</p>,
}))

import { SettingsPage } from './settings-page'

beforeEach(() => {
  mocks.section = 'profile'
})

describe('SettingsPage', () => {
  it('合法分区直接渲染对应内容，且内容区不再输出第二份目录', () => {
    render(<SettingsPage />)

    expect(screen.getByRole('heading', { name: '设置' })).toBeVisible()
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
    expect(screen.getByText('profile-section')).toBeVisible()
  })

  it('非法分区回落到默认的常规分区', () => {
    mocks.section = 'not-a-section'
    render(<SettingsPage />)

    expect(screen.getByText('general-section')).toBeVisible()
  })

  it('缺少分区参数时回落到默认的常规分区', () => {
    mocks.section = undefined
    render(<SettingsPage />)

    expect(screen.getByText('general-section')).toBeVisible()
  })

  it('使用统计分区渲染对应内容', () => {
    mocks.section = 'usage'
    render(<SettingsPage />)

    expect(screen.getByText('usage-section')).toBeVisible()
  })
})
