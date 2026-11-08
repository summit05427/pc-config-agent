import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/core/http'
import type { ModelUsageItem, ModelUsagePage } from '@/features/usage/api'

import { ModelUsagePanel } from './model-usage-panel'

const { getUsageMock } = vi.hoisted(() => ({ getUsageMock: vi.fn() }))

vi.mock('@/features/usage/api/model-usage', () => ({ getMyModelUsage: getUsageMock }))

const emptyPage: ModelUsagePage = {
  quota: {
    quotaType: 'DAILY',
    limit: 100,
    used: 12,
    resetAt: '2026-11-02T00:00:00Z',
  },
  list: [],
  total: 0,
  page: 1,
  size: 10,
  totalTokens: 0,
}

const usageItem: ModelUsageItem = {
  invocationId: 'inv-1',
  taskId: 'task-1',
  threadId: 'thread-1',
  modelRole: 'chat',
  provider: 'openai',
  modelKey: 'openai:gpt-4o',
  credentialSource: 'MANAGED',
  promptTokens: 120,
  completionTokens: 80,
  latencyMs: 950,
  status: 'SUCCESS',
  errorType: null,
  costStatus: 'ESTIMATED',
  costBearer: 'PLATFORM',
  currency: 'USD',
  estimatedCost: 0.0012,
  occurredAt: '2026-11-01T10:00:00Z',
}

const renderPanel = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  render(
    <QueryClientProvider client={queryClient}>
      <ModelUsagePanel />
    </QueryClientProvider>,
  )
}

describe('ModelUsagePanel', () => {
  it('没有调用记录时展示空态并仍显示额度', async () => {
    getUsageMock.mockResolvedValueOnce(emptyPage)
    renderPanel()

    expect(await screen.findByText('暂无调用记录。')).toBeInTheDocument()
    expect(screen.getByText('12 / 100')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('只保留时间、模型、来源与 Token 四列，且不再提供日期筛选', async () => {
    getUsageMock.mockResolvedValueOnce({ ...emptyPage, list: [usageItem], total: 1 })
    renderPanel()

    expect(await screen.findByRole('table')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: '时间' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: '模型' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: '来源' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Tokens' })).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: '延迟' })).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: '费用' })).not.toBeInTheDocument()
    expect(screen.getByText('120 / 80')).toBeInTheDocument()

    expect(screen.queryByLabelText('开始日期')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('结束日期')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '查询' })).not.toBeInTheDocument()
  })

  it('加载失败时展示错误并提供重试', async () => {
    getUsageMock.mockRejectedValue(new ApiError('用量服务异常', { status: 500 }))
    const user = userEvent.setup()
    renderPanel()

    expect(await screen.findByText('用量加载失败，请稍后重试。')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '重试' }))
    await waitFor(() => {
      expect(getUsageMock).toHaveBeenCalledTimes(2)
    })
  })
})
