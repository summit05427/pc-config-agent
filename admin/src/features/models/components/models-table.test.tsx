import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import type { AdminModelSummary } from '../types'
import { ModelsTable } from './models-table'

function model(overrides: Partial<AdminModelSummary> = {}): AdminModelSummary {
  return {
    provider: 'openai',
    modelKey: 'gpt-4o-mini',
    displayName: 'GPT-4o mini',
    contextWindow: 128000,
    capabilities: ['text', 'tool_calling'],
    capabilitySource: 'catalog',
    verifiedAt: null,
    enabled: true,
    providerEnabled: true,
    latestPricing: {
      id: 1,
      currency: 'USD',
      inputPricePerMillion: 0.15,
      outputPricePerMillion: 0.6,
      effectiveFrom: '2026-10-01T00:00:00Z',
      createdAt: '2026-10-01T00:00:00Z',
    },
    ...overrides,
  }
}

describe('ModelsTable', () => {
  it('renders model row with capabilities, status, and latest pricing', async () => {
    const { getByText, getByRole } = await render(
      <ModelsTable
        models={[model()]}
        isPending={false}
        hasError={false}
        isStatusUpdating={false}
        onOpenPricing={vi.fn()}
        onToggleStatus={vi.fn()}
        onRetry={vi.fn()}
      />
    )

    await expect.element(getByText('openai')).toBeInTheDocument()
    await expect.element(getByText('GPT-4o mini')).toBeInTheDocument()
    await expect.element(getByText('tool_calling')).toBeInTheDocument()
    await expect.element(getByText('启用中')).toBeInTheDocument()
    await expect
      .element(getByText('USD 输入 0.15 / 输出 0.6'))
      .toBeInTheDocument()
    await expect
      .element(getByRole('button', { name: '定价' }))
      .toBeInTheDocument()
    await expect
      .element(getByRole('button', { name: '停用' }))
      .toBeInTheDocument()
  })

  it('shows provider disabled status when provider is off', async () => {
    const { getByText } = await render(
      <ModelsTable
        models={[model({ providerEnabled: false })]}
        isPending={false}
        hasError={false}
        isStatusUpdating={false}
        onOpenPricing={vi.fn()}
        onToggleStatus={vi.fn()}
        onRetry={vi.fn()}
      />
    )

    await expect.element(getByText('Provider 已停用')).toBeInTheDocument()
  })

  it('renders empty state when no model matches', async () => {
    const { getByText } = await render(
      <ModelsTable
        models={[]}
        isPending={false}
        hasError={false}
        isStatusUpdating={false}
        onOpenPricing={vi.fn()}
        onToggleStatus={vi.fn()}
        onRetry={vi.fn()}
      />
    )

    await expect.element(getByText('没有符合条件的模型')).toBeInTheDocument()
  })

  it('renders error state when query failed', async () => {
    const { getByText } = await render(
      <ModelsTable
        models={[]}
        isPending={false}
        hasError
        isStatusUpdating={false}
        onOpenPricing={vi.fn()}
        onToggleStatus={vi.fn()}
        onRetry={vi.fn()}
      />
    )

    await expect.element(getByText('模型目录加载失败')).toBeInTheDocument()
  })
})
