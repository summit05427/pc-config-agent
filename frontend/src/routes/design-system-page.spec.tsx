import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import { useAppStore } from '@/app/stores/app-store'
import { TooltipProvider } from '@/shared/ui/tooltip'

import { DesignSystemPage } from './design-system-page'

const renderPage = () =>
  render(
    <TooltipProvider>
      <DesignSystemPage />
    </TooltipProvider>,
  )

describe('DesignSystemPage', () => {
  beforeEach(() => {
    window.localStorage.clear()
    useAppStore.getState().setTheme('system')
    useAppStore.getState().setSystemDark(false)
  })

  it('按主题按钮切换解析后的明暗主题', async () => {
    renderPage()

    expect(screen.getByText('当前解析主题：浅色')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'dark' }))

    expect(screen.getByText('当前解析主题：暗色')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'light' }))

    expect(screen.getByText('当前解析主题：浅色')).toBeInTheDocument()
  })

  it('渲染控件阶梯、表单与浮层示例', () => {
    renderPage()

    expect(
      screen.getByRole('heading', { name: '按钮（23 / 26 / 32 / 40 阶梯）' }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('输入框')).toBeInTheDocument()
    expect(screen.getByText('卡片')).toBeInTheDocument()
  })
})
