import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import type { AdminUsageItem } from '../types'
import { UsageTable } from './usage-table'

function usage(overrides: Partial<AdminUsageItem> = {}): AdminUsageItem {
  return {
    invocationId: '8f6d7c1e-0000-4000-8000-000000000001',
    taskId: '8f6d7c1e-0000-4000-8000-000000000002',
    userId: '11111111-1111-1111-1111-111111111111',
    username: 'demo',
    threadId: 'thread-1',
    modelRole: 'chat',
    provider: 'openai',
    modelKey: 'gpt-4o-mini',
    credentialSource: 'MANAGED',
    promptTokens: 120,
    completionTokens: 240,
    latencyMs: 1500,
    status: 'success',
    errorType: null,
    estimatedCost: 0.0125,
    costStatus: 'ESTIMATED',
    costBearer: 'PLATFORM',
    currency: 'USD',
    occurredAt: '2026-11-01T08:30:00Z',
    ...overrides,
  }
}

describe('UsageTable', () => {
  it('renders usage row with tokens, result and estimated cost', async () => {
    const { getByText } = await render(
      <UsageTable
        items={[usage()]}
        isPending={false}
        hasError={false}
        onRetry={vi.fn()}
      />
    )

    await expect.element(getByText('demo')).toBeInTheDocument()
    await expect.element(getByText('gpt-4o-mini')).toBeInTheDocument()
    await expect.element(getByText('平台托管')).toBeInTheDocument()
    await expect.element(getByText('120 / 240')).toBeInTheDocument()
    await expect.element(getByText('成功')).toBeInTheDocument()
    await expect.element(getByText('USD 0.0125')).toBeInTheDocument()
  })

  it('shows cost status instead of amount when cost is not estimated', async () => {
    const { getByText } = await render(
      <UsageTable
        items={[
          usage({
            credentialSource: 'BYOK',
            estimatedCost: null,
            costStatus: 'BYOK_NOT_BILLED',
            costBearer: 'USER',
            currency: null,
          }),
        ]}
        isPending={false}
        hasError={false}
        onRetry={vi.fn()}
      />
    )

    await expect.element(getByText('BYOK 不计费')).toBeInTheDocument()
    await expect.element(getByText('用户自带')).toBeInTheDocument()
  })

  it('renders empty state when no usage matches', async () => {
    const { getByText } = await render(
      <UsageTable
        items={[]}
        isPending={false}
        hasError={false}
        onRetry={vi.fn()}
      />
    )

    await expect
      .element(getByText('没有符合条件的用量记录'))
      .toBeInTheDocument()
  })

  it('renders error state when query failed', async () => {
    const { getByText } = await render(
      <UsageTable items={[]} isPending={false} hasError onRetry={vi.fn()} />
    )

    await expect.element(getByText('用量明细加载失败')).toBeInTheDocument()
  })
})
