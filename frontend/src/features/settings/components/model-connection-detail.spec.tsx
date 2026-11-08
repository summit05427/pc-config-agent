import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { ModelCatalogItem, ModelConnection } from '@/features/models/api'

import { ModelConnectionDetail } from './model-connection-detail'

const connection: ModelConnection = {
  id: 'conn-1',
  provider: 'openai',
  providerName: 'OpenAI',
  baseUrl: 'https://api.openai.com/v1',
  status: 'ACTIVE',
  lastVerifiedAt: '2026-11-01T08:00:00Z',
  createdAt: '2026-10-30T08:00:00Z',
  credential: {
    id: 'cred-1',
    maskedHint: 'sk-…9f2a',
    status: 'VERIFIED',
    createdAt: '2026-10-30T08:00:00Z',
  },
}

const models: ModelCatalogItem[] = [
  {
    provider: 'openai',
    modelKey: 'openai:gpt-4o',
    displayName: 'GPT-4o',
    capabilities: ['text', 'vision'],
    contextWindow: 128000,
  },
]

const renderDetail = (isBusy = false) => {
  const onBack = vi.fn()
  const onVerify = vi.fn()
  const onDelete = vi.fn()
  const onRotate = vi.fn().mockResolvedValue(undefined)

  render(
    <ModelConnectionDetail
      connection={connection}
      models={models}
      isBusy={isBusy}
      onBack={onBack}
      onVerify={onVerify}
      onRotate={onRotate}
      onDelete={onDelete}
    />,
  )

  return { onBack, onVerify, onDelete, onRotate }
}

describe('ModelConnectionDetail', () => {
  it('展示掩码凭证、验证状态与目录能力', () => {
    renderDetail()

    expect(screen.getByText('sk-…9f2a')).toBeInTheDocument()
    expect(screen.getByText('已验证')).toBeInTheDocument()
    expect(screen.getByText('GPT-4o')).toBeInTheDocument()
    expect(screen.getByText('上下文 128,000 tokens')).toBeInTheDocument()
  })

  it('验证与返回操作回传给父视图', async () => {
    const { onVerify, onBack } = renderDetail()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: '验证凭证' }))
    expect(onVerify).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole('button', { name: '返回' }))
    expect(onBack).toHaveBeenCalledTimes(1)
  })

  it('删除需二次确认后才回传操作', async () => {
    const { onDelete } = renderDetail()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: '删除' }))

    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: '删除' }))

    expect(onDelete).toHaveBeenCalledTimes(1)
  })

  it('轮换密钥提交新密钥并回传，成功后清空输入', async () => {
    const { onRotate } = renderDetail()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: '更换密钥' }))
    const dialog = await screen.findByRole('dialog')

    await user.type(
      within(dialog).getByLabelText('API Key'),
      'sk-rotated-abcdef123456',
    )
    await user.click(within(dialog).getByRole('button', { name: '保存新密钥' }))

    expect(onRotate).toHaveBeenCalledWith({
      apiKey: 'sk-rotated-abcdef123456',
      baseUrl: null,
    })
  })

  it('操作进行中时按钮禁用，避免重复提交', () => {
    renderDetail(true)

    expect(screen.getByRole('button', { name: '正在验证…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '删除' })).toBeDisabled()
  })
})
