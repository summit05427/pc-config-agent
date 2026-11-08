import { render, screen } from '@testing-library/react'
import { Component, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { OpenUiErrorBoundary } from './openui-error-boundary'

class ThrowingChild extends Component {
  render(): ReactNode {
    throw new Error('boom')
  }
}

const FALLBACK = <p>界面降级</p>

beforeEach(() => {
  // 错误边界用例会主动触发 React 的错误日志，抑制噪音但保留断言
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

describe('OpenUiErrorBoundary', () => {
  it('正常内容直接渲染', () => {
    render(
      <OpenUiErrorBoundary fallback={FALLBACK}>
        <p>渲染正常</p>
      </OpenUiErrorBoundary>,
    )

    expect(screen.getByText('渲染正常')).toBeInTheDocument()
    expect(screen.queryByText('界面降级')).toBeNull()
  })

  it('子节点抛错时只替换为降级内容', () => {
    render(
      <OpenUiErrorBoundary fallback={FALLBACK}>
        <ThrowingChild />
      </OpenUiErrorBoundary>,
    )

    expect(screen.getByText('界面降级')).toBeInTheDocument()
  })
})
