import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ModelCatalogItem } from '@/features/models/api'

import { ModelSelector } from './model-selector'

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
}))

const MODELS: readonly ModelCatalogItem[] = [
  {
    provider: 'openai',
    modelKey: 'openai:gpt-4o',
    displayName: 'GPT-4o',
    capabilities: [],
    contextWindow: null,
  },
]

describe('ModelSelector', () => {
  beforeEach(() => {
    navigateMock.mockClear()
  })

  it('Auto 模式触发器展示「Auto」，选择模型后回传 modelKey', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(<ModelSelector models={MODELS} modelKey={null} onChange={onChange} />)

    expect(screen.getByRole('combobox', { name: '模型' })).toHaveTextContent('Auto')

    await user.click(screen.getByRole('combobox', { name: '模型' }))
    await user.click(await screen.findByRole('option', { name: /GPT-4o/ }))

    expect(onChange).toHaveBeenCalledWith('openai:gpt-4o')
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('已选模型时触发器展示模型名称，目录缺失时退回原始 key', () => {
    render(<ModelSelector models={MODELS} modelKey="openai:gpt-4o" onChange={vi.fn()} />)
    expect(screen.getByRole('combobox', { name: '模型' })).toHaveTextContent('GPT-4o')

    render(<ModelSelector models={MODELS} modelKey="openai:unknown" onChange={vi.fn()} />)
    expect(screen.getAllByRole('combobox', { name: '模型' }).at(-1)).toHaveTextContent(
      'openai:unknown',
    )
  })

  it('选择「添加模型」跳转设置页模型分区，不触发模型切换', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(<ModelSelector models={MODELS} modelKey={null} onChange={onChange} />)

    await user.click(screen.getByRole('combobox', { name: '模型' }))
    await user.click(await screen.findByRole('option', { name: '添加模型' }))

    expect(navigateMock).toHaveBeenCalledWith({
      to: expect.stringContaining('/settings/$section'),
      params: { section: 'model' },
    })
    expect(onChange).not.toHaveBeenCalled()
  })
})
