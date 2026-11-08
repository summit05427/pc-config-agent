import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/core/http'
import type { ModelConnection } from '@/features/models/api'

import { ModelConnectionForm } from './model-connection-form'

const { createConnectionMock, onCreatedMock } = vi.hoisted(() => ({
  createConnectionMock: vi.fn(),
  onCreatedMock: vi.fn(),
}))

vi.mock('@/features/models/api', () => ({ createModelConnection: createConnectionMock }))

const connection: ModelConnection = {
  id: 'conn-1',
  provider: 'openai',
  providerName: 'OpenAI',
  baseUrl: 'https://api.openai.com/v1',
  status: 'ACTIVE',
  lastVerifiedAt: null,
  createdAt: '2026-10-30T08:00:00Z',
  credential: null,
}

const renderForm = (providerCode = 'openai') => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  render(
    <QueryClientProvider client={queryClient}>
      <ModelConnectionForm providerCode={providerCode} onCreated={onCreatedMock} />
    </QueryClientProvider>,
  )
}

describe('ModelConnectionForm', () => {
  it('渲染后接入地址为空，避免浏览器凭据自动填充污染', () => {
    renderForm()

    expect(screen.getByLabelText('接入地址')).toHaveValue('')
  })

  it('提交成功后清空地址与密钥，空地址转为 null 并回传连接', async () => {
    createConnectionMock.mockResolvedValueOnce(connection)
    const user = userEvent.setup()
    renderForm()

    await user.type(screen.getByLabelText('API Key'), 'sk-test-1234')
    await user.click(screen.getByRole('button', { name: '完成接入' }))

    await waitFor(() => {
      expect(createConnectionMock).toHaveBeenCalledWith(
        {
          providerCode: 'openai',
          baseUrl: null,
          apiKey: 'sk-test-1234',
        },
        expect.anything(),
      )
    })
    await waitFor(() => {
      expect(screen.getByLabelText('API Key')).toHaveValue('')
      expect(screen.getByLabelText('接入地址')).toHaveValue('')
      expect(onCreatedMock).toHaveBeenCalledWith(connection)
    })
  })

  it('密钥过短时在字段上提示且不调用接口', async () => {
    const user = userEvent.setup()
    renderForm()

    await user.type(screen.getByLabelText('API Key'), 'sk-123')
    await user.click(screen.getByRole('button', { name: '完成接入' }))

    expect(await screen.findByText('API Key 至少 8 个字符。')).toBeInTheDocument()
    expect(createConnectionMock).not.toHaveBeenCalled()
  })

  it('业务错误在表单顶部提示且不跳转', async () => {
    createConnectionMock.mockRejectedValueOnce(
      new ApiError('当前部署不支持该 Provider', { code: 40211, status: 400 }),
    )
    const user = userEvent.setup()
    renderForm()

    await user.type(screen.getByLabelText('API Key'), 'sk-test-1234')
    await user.click(screen.getByRole('button', { name: '完成接入' }))

    expect(await screen.findByText('当前部署不支持该 Provider')).toBeInTheDocument()
    expect(createConnectionMock).toHaveBeenCalledTimes(1)
    expect(onCreatedMock).not.toHaveBeenCalled()
  })
})
