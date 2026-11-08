import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

const envMock = vi.hoisted(() => ({
  appEnv: 'development',
  openUiEnabled: false,
}))

vi.mock('@/shared/lib/env', () => ({ env: envMock }))

import { MessageContent } from './message-content'

beforeAll(async () => {
  await import('@/features/generative-ui/components/openui-renderer-runtime')
})

const UI_BLOCK = '```openui\nroot = Stack([Text("动态内容", "heading")])\n```'

describe('MessageContent', () => {
  beforeEach(() => {
    envMock.openUiEnabled = false
  })

  it('开关关闭时保留原始 openui 围栏，按普通代码块展示', () => {
    const { container } = render(
      <MessageContent content={`前言\n\n${UI_BLOCK}\n\n结尾`} status="done" threadId="msg-off" />,
    )

    expect(container.querySelector('pre')).not.toBeNull()
    expect(container.textContent).toContain('root = Stack')
    expect(screen.getByText('前言')).toBeInTheDocument()
    expect(screen.getByText('结尾')).toBeInTheDocument()
  })

  it('开关打开但文本没有 UI 块时仍走原来的 Markdown 渲染', () => {
    envMock.openUiEnabled = true
    render(<MessageContent content={'## 普通标题\n\n正文'} status="done" threadId="msg-plain" />)

    expect(screen.getByRole('heading', { name: '普通标题' })).toBeInTheDocument()
    expect(screen.getByText('正文')).toBeInTheDocument()
  })

  it('已闭合 UI 块与前后 Markdown 同时渲染', async () => {
    envMock.openUiEnabled = true
    render(
      <MessageContent content={`前言\n\n${UI_BLOCK}\n\n结尾`} status="done" threadId="msg-mixed" />,
    )

    expect(screen.getByText('前言')).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: '动态内容' })).toBeInTheDocument()
    expect(screen.getByText('结尾')).toBeInTheDocument()
  })

  it('流式中未闭合的尾块显示占位', () => {
    envMock.openUiEnabled = true
    render(
      <MessageContent
        content={'前言\n\n```openui\nroot = Stack([Text("半截内容")'}
        status="streaming"
        threadId="msg-streaming"
      />,
    )

    expect(screen.getByText('前言')).toBeInTheDocument()
    expect(screen.getByText('正在生成动态界面…')).toBeInTheDocument()
    expect(screen.queryByText(/root = Stack/)).toBeNull()
  })

  it('终态仍未闭合的尾块降级为原文', () => {
    envMock.openUiEnabled = true
    render(
      <MessageContent
        content={'前言\n\n```openui\nroot = Stack([Text("半截内容")'}
        status="error"
        threadId="msg-incomplete"
      />,
    )

    expect(screen.getByText('动态界面未生成完整，已按原文显示。')).toBeInTheDocument()
    expect(screen.getByText(/root = Stack/)).toBeInTheDocument()
  })

  it('多个 UI 块互不影响', async () => {
    envMock.openUiEnabled = true
    render(
      <MessageContent
        content={
          '```openui\nroot = Stack([Text("第一块", "heading")])\n```\n\n' +
          '```openui\nroot = Stack([Text("第二块", "heading")])\n```'
        }
        status="done"
        threadId="msg-multiple"
      />,
    )

    expect(await screen.findByRole('heading', { name: '第一块' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '第二块' })).toBeInTheDocument()
  })

  it('UI 块动作转发给宿主回调', async () => {
    envMock.openUiEnabled = true
    const onContinueConversation = vi.fn()
    render(
      <MessageContent
        content={'```openui\nroot = Stack([Button("继续")])\n```'}
        status="done"
        threadId="msg-action"
        onContinueConversation={onContinueConversation}
      />,
    )

    await userEvent.click(await screen.findByRole('button', { name: '继续' }))

    expect(onContinueConversation).toHaveBeenCalledWith('继续')
  })
})
