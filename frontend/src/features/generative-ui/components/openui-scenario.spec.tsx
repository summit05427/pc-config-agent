import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

const envMock = vi.hoisted(() => ({
  appEnv: 'development',
  openUiEnabled: true,
}))

vi.mock('@/shared/lib/env', () => ({ env: envMock }))

import {
  HANGZHOU_TRIP_SCENARIO,
  PHONE_COMPARISON_SCENARIO,
  REIMBURSEMENT_SCENARIO,
  SCENARIO_FIXTURES,
} from '../testing/scenario-fixtures'
import { OpenUiRenderer } from './openui-renderer'

beforeAll(async () => {
  // 预热懒加载运行时，避免首个用例把 OpenUI 的首次转换时间算进断言超时
  await import('./openui-renderer-runtime')
})

/**
 * 真实场景验收。
 *
 * `component-contract.spec.tsx` 保证每个组件单独可渲染；这里保证「组件组合成
 * 完整回答」后交互仍然正确：标签页切换、折叠面板展开、表单提交、表格分页与流式禁用。
 */
describe('真实场景剧本', () => {
  beforeEach(() => {
    envMock.openUiEnabled = true
    window.sessionStorage.clear()
  })

  it.each(SCENARIO_FIXTURES)('$name 完整渲染', async ({ name, dsl, expectText }) => {
    render(<OpenUiRenderer response={dsl} />)

    const [firstText, ...restText] = expectText
    if (!firstText) {
      throw new Error(`剧本「${name}」缺少首条可见文本`)
    }
    expect(await screen.findByText(firstText)).toBeInTheDocument()
    for (const text of restText) {
      expect(screen.getByText(text)).toBeInTheDocument()
    }
  })

  it('行程剧本可切换标签页并展开折叠面板', async () => {
    render(<OpenUiRenderer response={HANGZHOU_TRIP_SCENARIO.dsl} />)

    expect(await screen.findByText('上午西湖，下午灵隐，傍晚河坊街。')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: '餐饮' }))
    expect(
      await screen.findByText('推荐知味观小笼与楼外楼西湖醋鱼，人均 80 元。'),
    ).toBeInTheDocument()

    // 折叠面板位于「贴士」标签页内，只有切换到该页才会挂载
    await userEvent.click(screen.getByRole('tab', { name: '贴士' }))
    await userEvent.click(screen.getByRole('button', { name: '天气' }))
    expect(await screen.findByText('春秋季多雨，随身带折叠伞。')).toBeInTheDocument()
  })

  it('行程剧本的追问建议点击后继续对话', async () => {
    const onContinueConversation = vi.fn()
    render(
      <OpenUiRenderer
        response={HANGZHOU_TRIP_SCENARIO.dsl}
        onContinueConversation={onContinueConversation}
      />,
    )

    await userEvent.click(await screen.findByRole('button', { name: '帮我查一下灵隐寺的门票价格' }))

    expect(onContinueConversation).toHaveBeenCalledWith('帮我查一下灵隐寺的门票价格')
  })

  it('报销剧本提交时回传全部字段值', async () => {
    const onSubmitForm = vi.fn()
    render(<OpenUiRenderer response={REIMBURSEMENT_SCENARIO.dsl} onSubmitForm={onSubmitForm} />)

    expect(await screen.findByLabelText('申请人')).toHaveValue('张三')

    await userEvent.click(screen.getByRole('checkbox', { name: '收据' }))
    await userEvent.click(screen.getByRole('radio', { name: '加急' }))
    await userEvent.type(screen.getByLabelText('发票号'), '1234567890')
    await userEvent.click(screen.getByRole('button', { name: '提交报销' }))

    expect(onSubmitForm).toHaveBeenCalledTimes(1)
    expect(onSubmitForm).toHaveBeenCalledWith(
      expect.objectContaining({
        formName: 'reimbursement-2026-11',
        fields: expect.objectContaining({
          applicant: '张三',
          amount: 320,
          category: 'travel',
          invoiceNo: '1234567890',
          attachments: ['invoice', 'receipt'],
          urgency: 'urgent',
        }),
      }),
    )
  })

  it('对比表超过 10 行时分页，翻页后展示第二页数据', async () => {
    render(<OpenUiRenderer response={PHONE_COMPARISON_SCENARIO.dsl} />)

    expect(await screen.findByText('iPhone 16')).toBeInTheDocument()
    expect(screen.queryByText('三星 Galaxy S24')).toBeNull()
    expect(screen.getByText(/1 \/ 2/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '下一页' }))

    expect(await screen.findByText('三星 Galaxy S24')).toBeInTheDocument()
    expect(screen.queryByText('iPhone 16')).toBeNull()
    expect(screen.getByText(/2 \/ 2/)).toBeInTheDocument()
  })

  it('流式期间禁止发送动作，但保留表格分页浏览', async () => {
    render(
      <OpenUiRenderer
        response={PHONE_COMPARISON_SCENARIO.dsl}
        isStreaming
        onContinueConversation={vi.fn()}
      />,
    )

    expect(await screen.findByText('iPhone 16')).toBeInTheDocument()
    // 追问会向助手发消息，流式期间必须禁用，避免和新轮次抢发送
    expect(screen.getByRole('button', { name: '预算 4000 元以内怎么选？' })).toBeDisabled()

    // 分页只改变本地浏览位置、不发送消息，流式期间仍可翻页
    await userEvent.click(screen.getByRole('button', { name: '下一页' }))
    expect(await screen.findByText('三星 Galaxy S24')).toBeInTheDocument()
  })
})
