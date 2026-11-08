import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { ThemeProvider } from '@/app/providers/theme-provider'
import { useAppStore } from '@/app/stores/app-store'

describe('ThemeProvider', () => {
  beforeEach(() => {
    document.documentElement.classList.remove('dark')
    useAppStore.setState({ theme: 'light', isSystemDark: false })
  })

  it('浅色主题下不添加 dark 类', () => {
    render(
      <ThemeProvider>
        <span>页面内容</span>
      </ThemeProvider>,
    )

    expect(document.documentElement.classList.contains('dark')).toBe(false)
    expect(screen.getByText('页面内容')).toBeInTheDocument()
  })

  it('切换到暗色主题后同步 dark 类', () => {
    render(
      <ThemeProvider>
        <span>页面内容</span>
      </ThemeProvider>,
    )

    act(() => {
      useAppStore.getState().setTheme('dark')
    })

    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('system 模式下按系统偏好决定 dark 类', () => {
    render(
      <ThemeProvider>
        <span>页面内容</span>
      </ThemeProvider>,
    )

    act(() => {
      useAppStore.getState().setTheme('system')
      useAppStore.getState().setSystemDark(true)
    })

    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })
})
