import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ModelUsagePage } from '@/features/usage/api'

import { UsageOverview } from './usage-overview'

const { getUsageMock } = vi.hoisted(() => ({ getUsageMock: vi.fn() }))

vi.mock('@/features/usage/api/model-usage', () => ({ getMyModelUsage: getUsageMock }))

const usagePage: ModelUsagePage = {
  quota: {
    quotaType: 'DAILY',
    limit: 100,
    used: 12,
    resetAt: '2026-11-02T00:00:00Z',
  },
  list: [],
  total: 0,
  page: 1,
  size: 1,
  totalTokens: 1234,
}

const renderOverview = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  render(
    <QueryClientProvider client={queryClient}>
      <UsageOverview />
    </QueryClientProvider>,
  )
}

describe('UsageOverview', () => {
  beforeEach(() => {
    getUsageMock.mockReset()
  })

  it('只展示累计 Token 数并格式化真实值', async () => {
    getUsageMock.mockResolvedValue(usagePage)
    renderOverview()

    expect(screen.getByText('累计 Token 数')).toBeInTheDocument()
    expect(await screen.findByText('1,234')).toBeInTheDocument()
    expect(screen.queryByText('峰值 Token 数')).not.toBeInTheDocument()
  })

  it('加载失败时给出提示', async () => {
    getUsageMock.mockRejectedValue(new Error('boom'))
    renderOverview()

    expect(await screen.findByText('用量数据加载失败，请稍后重试。')).toBeInTheDocument()
  })
})
