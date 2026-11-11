import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { QuickPromptPicker } from './quick-prompt-picker'

describe('QuickPromptPicker', () => {
  it('累积选择后拼成一段完整描述', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()

    render(<QuickPromptPicker onConfirm={onConfirm} />)

    await user.click(screen.getByRole('button', { name: '需求向导' }))
    await user.click(screen.getByRole('button', { name: '8000–12000 元' }))
    await user.click(screen.getByRole('button', { name: '3A 单机游戏' }))
    await user.click(screen.getByRole('button', { name: '编程开发' }))

    expect(screen.getByText('已选 3 项')).toBeVisible()

    await user.click(screen.getByRole('button', { name: '生成描述' }))

    expect(onConfirm).toHaveBeenCalledWith(
      '预算：8000–12000 元；主要用途：3A 单机游戏、编程开发。请按以上需求推荐一套整机配置，并说明总价与兼容性。',
    )
  })

  it('互斥组后选覆盖先选，数量不累加', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()

    render(<QuickPromptPicker onConfirm={onConfirm} />)

    await user.click(screen.getByRole('button', { name: '需求向导' }))
    await user.click(screen.getByRole('button', { name: '5000 元以内' }))
    await user.click(screen.getByRole('button', { name: '8000–12000 元' }))

    expect(screen.getByText('已选 1 项')).toBeVisible()
    expect(screen.getByRole('button', { name: '5000 元以内' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
  })

  it('未选择任何条件时确认按钮禁用', async () => {
    const user = userEvent.setup()

    render(<QuickPromptPicker onConfirm={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: '需求向导' }))

    expect(screen.getByRole('button', { name: '生成描述' })).toBeDisabled()
  })
})
