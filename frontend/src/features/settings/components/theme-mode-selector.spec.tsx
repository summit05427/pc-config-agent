import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { useAppStore } from '@/app/stores/app-store'
import zhCN from '@/locales/zh-CN'

import { ThemeModeSelector } from './theme-mode-selector'

/** 通过单选的可访问名称取到外层卡片，避免依赖 DOM 层级 */
const cardFor = (label: string): HTMLElement =>
  screen.getByRole('radio', { name: label }).closest('label') as HTMLElement

describe('ThemeModeSelector', () => {
  beforeEach(() => {
    useAppStore.getState().setTheme('system')
  })

  it('渲染三张主题卡，当前主题同时处于选中与展开状态', () => {
    render(<ThemeModeSelector />)

    expect(screen.getAllByRole('radio')).toHaveLength(3)

    const systemRadio = screen.getByRole('radio', { name: zhCN.theme.system })
    expect(systemRadio).toBeChecked()
    expect(cardFor(zhCN.theme.system)).toHaveAttribute('data-expanded', 'true')
    expect(cardFor(zhCN.theme.system).style.flexGrow).toBe('1.6')
    expect(cardFor(zhCN.theme.light)).toHaveAttribute('data-expanded', 'false')
  })

  it('点击主题卡写入 app-store 并立即退出预览态，其余卡片恢复清晰', () => {
    render(<ThemeModeSelector />)

    const darkRadio = screen.getByRole('radio', { name: zhCN.theme.dark })
    fireEvent.mouseOver(cardFor(zhCN.theme.dark))
    fireEvent.click(darkRadio)

    expect(useAppStore.getState().theme).toBe('dark')
    expect(darkRadio).toBeChecked()
    expect(cardFor(zhCN.theme.dark)).toHaveAttribute('data-expanded', 'true')
    expect(cardFor(zhCN.theme.dark).style.flexGrow).toBe('1.6')
    expect(cardFor(zhCN.theme.light)).toHaveAttribute('data-dimmed', 'false')
    expect(cardFor(zhCN.theme.system)).toHaveAttribute('data-dimmed', 'false')
  })

  it('悬浮时展开对应卡片，指针移出后回落到选中项', () => {
    render(<ThemeModeSelector />)

    const group = screen.getByRole('radiogroup', { name: zhCN.settings.appearance.theme })
    const lightCard = cardFor(zhCN.theme.light)

    fireEvent.mouseOver(lightCard)
    expect(lightCard).toHaveAttribute('data-expanded', 'true')
    expect(lightCard.style.flexGrow).toBe('1.6')
    expect(cardFor(zhCN.theme.system)).toHaveAttribute('data-expanded', 'false')
    expect(cardFor(zhCN.theme.system)).toHaveAttribute('data-dimmed', 'true')

    fireEvent.mouseOut(group)
    expect(cardFor(zhCN.theme.system)).toHaveAttribute('data-expanded', 'true')
    expect(cardFor(zhCN.theme.system).style.flexGrow).toBe('1.6')
    expect(lightCard).toHaveAttribute('data-dimmed', 'false')
  })

  it('键盘聚焦时展开对应卡片，失焦后回落到选中项', () => {
    render(<ThemeModeSelector />)

    const lightRadio = screen.getByRole('radio', { name: zhCN.theme.light })

    fireEvent.focus(lightRadio)
    expect(cardFor(zhCN.theme.light)).toHaveAttribute('data-expanded', 'true')
    expect(cardFor(zhCN.theme.system)).toHaveAttribute('data-dimmed', 'true')

    fireEvent.blur(lightRadio)
    expect(cardFor(zhCN.theme.system)).toHaveAttribute('data-expanded', 'true')
    expect(cardFor(zhCN.theme.light)).toHaveAttribute('data-dimmed', 'false')
  })
})
