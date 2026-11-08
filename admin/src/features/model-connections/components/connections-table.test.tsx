import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import type { AdminModelConnection } from '../types'
import { ConnectionsTable } from './connections-table'

function connection(
  overrides: Partial<AdminModelConnection> = {}
): AdminModelConnection {
  return {
    id: '44444444-4444-4444-4444-444444444444',
    userId: '11111111-1111-1111-1111-111111111111',
    username: 'demo',
    displayName: '演示账号',
    provider: 'openai',
    providerName: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
    status: 'ACTIVE',
    lastVerifiedAt: '2026-11-01T09:00:00Z',
    createdAt: '2026-11-01T09:00:00Z',
    credential: {
      id: '55555555-5555-5555-5555-555555555555',
      maskedHint: 'sk-****abcd',
      status: 'VERIFIED',
      createdAt: '2026-11-01T09:00:00Z',
    },
    ...overrides,
  }
}

describe('ConnectionsTable', () => {
  it('renders connection with masked credential and verified status', async () => {
    const { getByText } = await render(
      <ConnectionsTable
        connections={[connection()]}
        isPending={false}
        hasError={false}
        onRetry={vi.fn()}
      />
    )

    await expect.element(getByText('演示账号')).toBeInTheDocument()
    await expect
      .element(getByText('OpenAI', { exact: true }))
      .toBeInTheDocument()
    await expect
      .element(getByText('https://api.openai.com/v1', { exact: true }))
      .toBeInTheDocument()
    await expect.element(getByText('有效')).toBeInTheDocument()
    await expect.element(getByText('sk-****abcd')).toBeInTheDocument()
    await expect.element(getByText('已验证')).toBeInTheDocument()
  })

  it('shows deleted status and no credential hint when credential is absent', async () => {
    const { getByText } = await render(
      <ConnectionsTable
        connections={[connection({ status: 'DELETED', credential: null })]}
        isPending={false}
        hasError={false}
        onRetry={vi.fn()}
      />
    )

    await expect.element(getByText('已删除')).toBeInTheDocument()
    await expect.element(getByText('无有效凭证')).toBeInTheDocument()
  })

  it('renders empty state when no connection matches', async () => {
    const { getByText } = await render(
      <ConnectionsTable
        connections={[]}
        isPending={false}
        hasError={false}
        onRetry={vi.fn()}
      />
    )

    await expect
      .element(getByText('没有符合条件的模型连接'))
      .toBeInTheDocument()
  })

  it('renders error state when query failed', async () => {
    const { getByText } = await render(
      <ConnectionsTable
        connections={[]}
        isPending={false}
        hasError
        onRetry={vi.fn()}
      />
    )

    await expect.element(getByText('模型连接加载失败')).toBeInTheDocument()
  })
})
