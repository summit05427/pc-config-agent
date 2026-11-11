import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { FeedbackSummary } from './feedback-summary'

describe('FeedbackSummary', () => {
  it('renders up/down counts and reason distribution', async () => {
    const { getByText } = await render(
      <FeedbackSummary
        summary={{
          upCount: 30,
          downCount: 10,
          reasons: [
            { reasonCode: 'INACCURATE', label: '信息不准确', total: 6 },
            { reasonCode: 'INCOMPLETE', label: '回答不完整', total: 4 },
          ],
        }}
        isPending={false}
        hasError={false}
      />
    )

    await expect.element(getByText('30')).toBeInTheDocument()
    await expect.element(getByText('10')).toBeInTheDocument()
    await expect.element(getByText('差评占比 25.0%')).toBeInTheDocument()
    await expect.element(getByText('信息不准确')).toBeInTheDocument()
    await expect.element(getByText('回答不完整')).toBeInTheDocument()
  })

  it('renders empty state when no feedback exists', async () => {
    const { getByText } = await render(
      <FeedbackSummary
        summary={{ upCount: 0, downCount: 0, reasons: [] }}
        isPending={false}
        hasError={false}
      />
    )

    await expect.element(getByText('当前筛选范围内暂无反馈数据。')).toBeInTheDocument()
  })

  it('renders error state when summary request failed', async () => {
    const { getByText } = await render(
      <FeedbackSummary summary={undefined} isPending={false} hasError />
    )

    await expect
      .element(getByText('反馈聚合加载失败，请稍后重试。'))
      .toBeInTheDocument()
  })
})
