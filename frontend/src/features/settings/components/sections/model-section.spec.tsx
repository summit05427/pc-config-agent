import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/core/http'

import { ModelSection } from './model-section'

const { verifyMock, deleteMock, queryState } = vi.hoisted(() => ({
  verifyMock: vi.fn(),
  deleteMock: vi.fn(),
  // 供应商目录查询的错误开关：用于区分「真正未启用」与「加载失败」
  queryState: { providerError: null as Error | null },
}))

vi.mock('@/features/models/api', () => {
  const catalog = [
    {
      provider: 'openai',
      modelKey: 'openai:gpt-4o',
      displayName: 'GPT-4o',
      capabilities: ['text', 'vision'],
      contextWindow: 128000,
    },
    {
      provider: 'deepseek',
      modelKey: 'deepseek:deepseek-v4-pro',
      displayName: 'DeepSeek V4 Pro',
      capabilities: ['text'],
      contextWindow: null,
    },
  ]
  const connections = [
    {
      id: 'conn-1',
      provider: 'openai',
      providerName: 'OpenAI',
      baseUrl: 'https://api.openai.com/v1',
      status: 'ACTIVE',
      lastVerifiedAt: null,
      createdAt: '2026-10-30T08:00:00Z',
      credential: {
        id: 'cred-1',
        maskedHint: 'sk-…9f2a',
        status: 'VERIFIED',
        createdAt: '2026-10-30T08:00:00Z',
      },
    },
  ]
  const page = <T,>(list: T[]) => ({ list, total: list.length, page: 1, size: 100 })
  const providers = [
    {
      code: 'deepseek',
      displayName: 'DeepSeek',
      protocol: 'openai',
      defaultBaseUrl: 'https://api.deepseek.com/v1',
      modelCount: 2,
    },
    {
      code: 'openai',
      displayName: 'OpenAI',
      protocol: 'openai',
      defaultBaseUrl: 'https://api.openai.com/v1',
      modelCount: 2,
    },
  ]

  return {
    modelCatalogQueryOptions: {
      queryKey: ['models', 'catalog', 'section-spec'],
      queryFn: () => Promise.resolve(page(catalog)),
    },
    modelConnectionsQueryOptions: {
      queryKey: ['models', 'connections', 'section-spec'],
      queryFn: () => Promise.resolve(page(connections)),
    },
    modelProvidersQueryOptions: {
      queryKey: ['models', 'providers', 'section-spec'],
      queryFn: () =>
        queryState.providerError
          ? Promise.reject(queryState.providerError)
          : Promise.resolve(providers),
    },
    // useMutation 会额外传入 context 参数，这里包一层只保留业务参数，断言更精确
    verifyModelConnection: (connectionId: string) => verifyMock(connectionId),
    deleteModelConnection: (connectionId: string) => deleteMock(connectionId),
    updateModelConnection: vi.fn(),
    createModelConnection: vi.fn(),
  }
})

const renderSection = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  render(
    <QueryClientProvider client={queryClient}>
      <ModelSection />
    </QueryClientProvider>,
  )
}

describe('ModelSection', () => {
  beforeEach(() => {
    queryState.providerError = null
  })

  it('默认视图展示供应商列表，并能进入详情后返回', async () => {
    renderSection()
    const user = userEvent.setup()

    expect(await screen.findByText('接入的供应商')).toBeInTheDocument()
    expect(screen.queryByText('模型用量')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /OpenAI/ }))
    expect(await screen.findByText('sk-…9f2a')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '返回' }))
    expect(await screen.findByText('接入的供应商')).toBeInTheDocument()
  })

  it('从添加供应商进入品牌选择，再进入接入表单', async () => {
    renderSection()
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: '添加供应商' }))
    expect(await screen.findByText('选择供应商')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /DeepSeek/ }))
    expect(await screen.findByText('接入 DeepSeek')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '完成接入' })).toBeInTheDocument()
  })

  it('只有 40209 才提示未启用，其它错误展示加载失败与重试', async () => {
    queryState.providerError = new ApiError('byok disabled', { code: 40209, status: 404 })
    renderSection()
    expect(
      await screen.findByText('当前部署未启用自带密钥（BYOK），无法配置模型连接。'),
    ).toBeInTheDocument()
  })

  it('接口 500 时不得误报为未启用', async () => {
    queryState.providerError = new ApiError('boom', { code: 500, status: 500 })
    renderSection()
    expect(await screen.findByText('模型配置加载失败，请稍后重试。')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重新加载' })).toBeInTheDocument()
    expect(
      screen.queryByText('当前部署未启用自带密钥（BYOK），无法配置模型连接。'),
    ).not.toBeInTheDocument()
  })

  it('详情内验证与删除都按连接 id 调用接口', async () => {
    verifyMock.mockResolvedValueOnce({})
    deleteMock.mockResolvedValueOnce(undefined)
    renderSection()
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: /OpenAI/ }))
    await user.click(screen.getByRole('button', { name: '验证凭证' }))
    expect(verifyMock).toHaveBeenCalledWith('conn-1')

    await user.click(screen.getByRole('button', { name: '删除' }))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: '删除' }))
    expect(deleteMock).toHaveBeenCalledWith('conn-1')
  })
})
