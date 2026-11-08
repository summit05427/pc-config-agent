import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Switch } from '@/shared/ui/switch'

describe('Switch', () => {
  it('通过 role=switch 暴露可访问性状态并在点击后切换', async () => {
    const user = userEvent.setup()
    const onCheckedChange = vi.fn()

    render(<Switch aria-label="启用通知" onCheckedChange={onCheckedChange} />)

    const control = screen.getByRole('switch', { name: '启用通知' })
    expect(control).toHaveAttribute('aria-checked', 'false')

    await user.click(control)

    expect(control).toHaveAttribute('aria-checked', 'true')
    expect(onCheckedChange).toHaveBeenCalledWith(true)
  })

  it('禁用态点击不改变状态', async () => {
    const user = userEvent.setup()

    render(<Switch aria-label="启用通知" disabled />)

    const control = screen.getByRole('switch', { name: '启用通知' })
    await user.click(control)

    expect(control).toHaveAttribute('aria-checked', 'false')
  })
})
