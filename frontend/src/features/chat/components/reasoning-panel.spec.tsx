import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { ReasoningPanel } from './reasoning-panel'

describe('ReasoningPanel', () => {
  it('没有思考内容时不渲染任何节点', () => {
    const { container } = render(<ReasoningPanel text="   " live />)

    expect(container).toBeEmptyDOMElement()
  })

  it('流式期间默认展开，生成结束后默认收起', () => {
    const { rerender } = render(<ReasoningPanel text="先分析问题" live />)

    expect(screen.getByText('先分析问题')).toBeInTheDocument()
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'true')

    rerender(<ReasoningPanel text="先分析问题" live={false} />)

    expect(screen.queryByText('先分析问题')).toBeNull()
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'false')
  })

  it('生成结束后用户仍可手动展开查看', async () => {
    render(<ReasoningPanel text="先分析问题" />)

    await userEvent.click(screen.getByRole('button'))

    expect(screen.getByText('先分析问题')).toBeInTheDocument()
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'true')
  })
})
