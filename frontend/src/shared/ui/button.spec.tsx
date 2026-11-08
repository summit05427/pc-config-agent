import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Button } from '@/shared/ui/button'

describe('Button', () => {
  it('默认尺寸取 CDS 中号控件高度与 8px 圆角', () => {
    render(<Button>确定</Button>)

    const button = screen.getByRole('button', { name: '确定' })

    expect(button).toHaveAttribute('data-slot', 'button')
    expect(button.className).toContain('h-[var(--control-height-md)]')
    expect(button.className).toContain('rounded-[var(--cds-radius-btn-md)]')
  })

  it('sm 尺寸取 26px 阶梯并使用 6px 圆角', () => {
    render(<Button size="sm">确定</Button>)

    const button = screen.getByRole('button', { name: '确定' })

    expect(button.className).toContain('h-[var(--control-height-sm)]')
    expect(button.className).toContain('rounded-[var(--cds-radius-btn-xs)]')
  })

  it('禁用态不可交互', () => {
    render(<Button disabled>提交</Button>)

    expect(screen.getByRole('button', { name: '提交' })).toBeDisabled()
  })

  it('asChild 渲染为链接且保留按钮样式', () => {
    render(
      <Button asChild>
        <a href="/chat">进入会话</a>
      </Button>,
    )

    const link = screen.getByRole('link', { name: '进入会话' })

    expect(link).toHaveAttribute('href', '/chat')
    expect(link.className).toContain('h-[var(--control-height-md)]')
  })
})
