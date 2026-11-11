import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import type { AdminFeedbackItem } from '../types'
import { FeedbackTable } from './feedback-table'

function feedback(overrides: Partial<AdminFeedbackItem> = {}): AdminFeedbackItem {
  return {
    userId: '11111111-1111-1111-1111-111111111111',
    username: 'demo',
    threadId: 'thread-1',
    messageId: 'thread-1:3',
    rating: 'DOWN',
    reasonCode: 'OFF_TOPIC',
    comment: '没有回答我的问题',
    createdAt: '2026-11-01T08:30:00Z',
    ...overrides,
  }
}

describe('FeedbackTable', () => {
  it('renders feedback row with rating, reason and comment', async () => {
    const { getByText } = await render(
      <FeedbackTable items={[feedback()]} isPending={false} hasError={false} onRetry={vi.fn()} />
    )

    await expect.element(getByText('demo')).toBeInTheDocument()
    await expect.element(getByText('thread-1:3')).toBeInTheDocument()
    await expect.element(getByText('踩')).toBeInTheDocument()
    await expect.element(getByText('答非所问')).toBeInTheDocument()
    await expect.element(getByText('没有回答我的问题')).toBeInTheDocument()
  })

  it('shows placeholder when user deleted and comment missing', async () => {
    const { getByText } = await render(
      <FeedbackTable
        items={[feedback({ username: null, rating: 'UP', reasonCode: null, comment: null })]}
        isPending={false}
        hasError={false}
        onRetry={vi.fn()}
      />
    )

    await expect.element(getByText('用户已删除')).toBeInTheDocument()
    await expect.element(getByText('赞')).toBeInTheDocument()
    // 原因与备注各有一处占位符
    await expect.element(getByText('—').first()).toBeInTheDocument()
  })

  it('renders empty state when no feedback matches', async () => {
    const { getByText } = await render(
      <FeedbackTable items={[]} isPending={false} hasError={false} onRetry={vi.fn()} />
    )

    await expect.element(getByText('没有符合条件的反馈')).toBeInTheDocument()
  })

  it('renders error state with retry action', async () => {
    const { getByText } = await render(
      <FeedbackTable items={[]} isPending={false} hasError onRetry={vi.fn()} />
    )

    await expect.element(getByText('反馈明细加载失败')).toBeInTheDocument()
  })
})
