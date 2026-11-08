import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ModelProviderPicker } from './model-provider-picker'

const renderPicker = () => {
  const onSelect = vi.fn()
  const onBack = vi.fn()

  render(
    <ModelProviderPicker
      providers={['openai', 'deepseek', 'qwen']}
      configuredProviderCodes={new Set(['openai'])}
      modelCounts={
        new Map([
          ['openai', 2],
          ['deepseek', 2],
          ['qwen', 0],
        ])
      }
      onSelect={onSelect}
      onBack={onBack}
    />,
  )

  return { onSelect, onBack }
}

describe('ModelProviderPicker', () => {
  it('已接入供应商禁用并标注状态，未接入项展示模型数量', () => {
    renderPicker()

    expect(screen.getByRole('button', { name: /OpenAI/ })).toBeDisabled()
    expect(screen.getByText('已接入')).toBeInTheDocument()
    expect(screen.getByText('暂无登记的模型')).toBeInTheDocument()
  })

  it('点击未接入供应商回传 provider code', async () => {
    const { onSelect } = renderPicker()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: /DeepSeek/ }))

    expect(onSelect).toHaveBeenCalledWith('deepseek')
  })

  it('返回按钮回到默认视图', async () => {
    const { onBack } = renderPicker()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: '返回' }))

    expect(onBack).toHaveBeenCalledTimes(1)
  })
})
