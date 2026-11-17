import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

const envMock = vi.hoisted(() => ({
  appEnv: 'development',
  openUiEnabled: true,
}))

vi.mock('@/shared/lib/env', () => ({ env: envMock }))

import { OpenUiBlock } from './openui-block'

beforeAll(async () => {
  await import('./openui-renderer-runtime')
})

const ACTION_RESPONSE = `root = Stack([
  Text("动态内容", "heading"),
  Button("继续")
])`

const FORM_RESPONSE = `root = Stack([
  Form("contact", Button("提交"), [
    TextInput("name", "姓名", "请输入姓名")
  ])
])`

const FORM_WITH_TEXT_RESPONSE = `root = Stack([
  Text("表单消息", "heading"),
  Form("contact", Button("提交"), [
    TextInput("name", "姓名", "请输入姓名")
  ])
])`

describe('OpenUiBlock', () => {
  beforeEach(() => {
    envMock.openUiEnabled = true
  })

  it('流式中的未闭合块只显示占位，不渲染半截 DSL', () => {
    render(
      <OpenUiBlock
        threadId="block-thread-streaming"
        content={'root = Stack([\n  Text("半截内容")'}
        isComplete={false}
        isMessageStreaming
      />,
    )

    expect(screen.getByText('正在生成动态界面…')).toBeInTheDocument()
    expect(screen.queryByText(/root = Stack/)).toBeNull()
  })

  it('终态仍未闭合时降级为原文并给出提示', () => {
    render(
      <OpenUiBlock
        threadId="block-thread-incomplete"
        content={'root = Stack([\n  Text("半截内容")'}
        isComplete={false}
        isMessageStreaming={false}
      />,
    )

    expect(screen.getByText('动态界面未生成完整，已按原文显示。')).toBeInTheDocument()
    expect(screen.getByText(/root = Stack/)).toBeInTheDocument()
  })

  it('已闭合块交给渲染器并转发继续对话动作', async () => {
    const onContinueConversation = vi.fn()
    render(
      <OpenUiBlock
        threadId="block-thread-complete"
        content={ACTION_RESPONSE}
        isComplete
        isMessageStreaming={false}
        onContinueConversation={onContinueConversation}
      />,
    )

    expect(await screen.findByText('动态内容')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '继续' }))

    expect(onContinueConversation).toHaveBeenCalledWith('继续')
  })

  it('消息仍在流式时已闭合块的交互保持禁用', async () => {
    render(
      <OpenUiBlock
        threadId="block-thread-live"
        content={ACTION_RESPONSE}
        isComplete
        isMessageStreaming
        onContinueConversation={vi.fn()}
      />,
    )

    expect(await screen.findByText('动态内容')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '继续' })).toBeDisabled()
  })

  it('存在待澄清中断时屏蔽生成式表单，避免与 HITL 双入口', async () => {
    render(
      <OpenUiBlock
        threadId="block-thread-hitl"
        content={FORM_WITH_TEXT_RESPONSE}
        isComplete
        isMessageStreaming={false}
        disableForms
      />,
    )

    // 渲染器正常工作，只是 Form 被上下文隐藏
    expect(await screen.findByText('表单消息')).toBeInTheDocument()
    expect(screen.queryByLabelText('姓名')).toBeNull()
  })

  it('实时消息换成历史消息重挂载后，表单已填内容仍能恢复', async () => {
    const props = {
      threadId: 'block-thread-form',
      content: FORM_RESPONSE,
      isComplete: true,
      isMessageStreaming: false,
    }
    const first = render(<OpenUiBlock {...props} />)

    await userEvent.type(await screen.findByLabelText('姓名'), '张三')
    first.unmount()

    render(<OpenUiBlock {...props} />)

    expect(await screen.findByLabelText('姓名')).toHaveValue('张三')
  })
})
