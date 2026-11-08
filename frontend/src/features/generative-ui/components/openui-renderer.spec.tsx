import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode } from 'react'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

const envMock = vi.hoisted(() => ({
  appEnv: 'development',
  openUiEnabled: false,
}))

vi.mock('@/shared/lib/env', () => ({ env: envMock }))

import { OpenUiRenderer } from './openui-renderer'

beforeAll(async () => {
  // 预热懒加载模块，避免首个用例把 OpenUI 运行时的首次转换时间算进断言超时
  await import('./openui-renderer-runtime')
})

const STATIC_RESPONSE = `root = Stack([
  Text("生成式界面标题", "heading"),
  Badge("运行正常", "success")
])`

const ACTIONS_RESPONSE = `root = Stack([
  Button("继续对话"),
  Button("打开链接", @OpenUrl("https://example.com"))
])`

const OFFICIAL_PRIMITIVES_RESPONSE = `root = Stack([
  Tabs([
    TabItem("t1", "概览", [Text("第一个标签")]),
    TabItem("t2", "详情", [Text("第三个标签")])
  ]),
  Accordion([AccordionItem("a1", "展开第一节", [Text("折叠内容")])]),
  Table([Col("名称", ["甲", "乙"]), Col("数量", [1, 2])]),
  MetricIndicator("42%")
])`

const DISPLAY_RESPONSE = `root = Stack([
  Image("https://example.com/cover.png", "示例图"),
  Progress(40, "处理中"),
  StatGroup([StatItem("42%", "转化率"), StatItem("120", "订单数")]),
  Timeline([TimelineItem("下单", "创建订单"), TimelineItem("发货", "仓库出库")])
])`

const FORM_RESPONSE = `root = Stack([
  Form("contact", Button("提交"), [
    TextInput("name", "姓名", "请输入姓名"),
    NumberInput("age", "年龄"),
    Select("plan", "套餐", [SelectOption("basic", "基础版"), SelectOption("pro", "专业版")]),
    CheckboxGroup("features", "功能", [CheckboxOption("export", "导出"), CheckboxOption("api", "API")]),
    RadioGroup("speed", "响应速度", [RadioOption("fast", "快速"), RadioOption("stable", "稳定")])
  ])
])`

describe('OpenUiRenderer', () => {
  beforeEach(() => {
    envMock.openUiEnabled = false
  })

  it('开关关闭时不渲染任何内容', () => {
    const { container } = render(<OpenUiRenderer response={STATIC_RESPONSE} />)

    expect(container).toBeEmptyDOMElement()
  })

  it('开关打开后按组件库渲染 OpenUI Lang', async () => {
    envMock.openUiEnabled = true
    render(<OpenUiRenderer response={STATIC_RESPONSE} />)

    expect(await screen.findByText('生成式界面标题')).toBeInTheDocument()
    expect(screen.getByText('运行正常')).toBeInTheDocument()
  })

  it('StrictMode 下不会重复挂载出多份内容', async () => {
    envMock.openUiEnabled = true
    render(
      <StrictMode>
        <OpenUiRenderer response={STATIC_RESPONSE} />
      </StrictMode>,
    )

    expect(await screen.findAllByText('生成式界面标题')).toHaveLength(1)
  })

  it('流式未闭合时仍渲染已到达的部分', async () => {
    envMock.openUiEnabled = true
    render(<OpenUiRenderer response={'root = Stack([\n  Text("流式内容")'} isStreaming />)

    expect(await screen.findByText('流式内容')).toBeInTheDocument()
  })

  it('未注册组件不会崩溃，也不会渲染其内容', async () => {
    envMock.openUiEnabled = true
    render(
      <OpenUiRenderer
        response={`root = Stack([
  Text("可见内容"),
  Unknown("未注册组件")
])`}
      />,
    )

    expect(await screen.findByText('可见内容')).toBeInTheDocument()
    expect(screen.queryByText('未注册组件')).toBeNull()
  })

  it('非法属性被校验拦截且不影响同块其他组件', async () => {
    envMock.openUiEnabled = true
    render(
      <OpenUiRenderer
        response={`root = Stack([
  Text("合法内容"),
  Badge(123)
])`}
      />,
    )

    expect(await screen.findByText('合法内容')).toBeInTheDocument()
    expect(screen.queryByText('123')).toBeNull()
  })

  it('无 action 的按钮把文案作为继续对话消息', async () => {
    envMock.openUiEnabled = true
    const onContinueConversation = vi.fn()
    render(
      <OpenUiRenderer response={ACTIONS_RESPONSE} onContinueConversation={onContinueConversation} />,
    )

    await userEvent.click(await screen.findByRole('button', { name: '继续对话' }))

    expect(onContinueConversation).toHaveBeenCalledWith('继续对话')
  })

  it('http/https 链接转发给宿主回调', async () => {
    envMock.openUiEnabled = true
    const onOpenUrl = vi.fn()
    render(<OpenUiRenderer response={ACTIONS_RESPONSE} onOpenUrl={onOpenUrl} />)

    await userEvent.click(await screen.findByRole('button', { name: '打开链接' }))

    expect(onOpenUrl).toHaveBeenCalledWith('https://example.com')
  })

  it('危险协议链接被拒绝，不触发宿主回调', async () => {
    envMock.openUiEnabled = true
    const onOpenUrl = vi.fn()
    render(
      <OpenUiRenderer
        response={`root = Stack([
  Button("危险链接", @OpenUrl("javascript:alert(1)"))
])`}
        onOpenUrl={onOpenUrl}
      />,
    )

    await userEvent.click(await screen.findByRole('button', { name: '危险链接' }))

    expect(onOpenUrl).not.toHaveBeenCalled()
  })

  it('官方原语适配组件按约定契约渲染', async () => {
    envMock.openUiEnabled = true
    render(<OpenUiRenderer response={OFFICIAL_PRIMITIVES_RESPONSE} />)

    expect(await screen.findByText('第一个标签')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '详情' })).toBeInTheDocument()
    expect(screen.getByText('折叠内容')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: '名称' })).toBeInTheDocument()
    expect(screen.getByText('甲')).toBeInTheDocument()
    expect(screen.getByText('42%')).toBeInTheDocument()
  })

  it('追问建议点击后以建议文案继续对话', async () => {
    envMock.openUiEnabled = true
    const onContinueConversation = vi.fn()
    render(
      <OpenUiRenderer
        response={`root = Stack([FollowUpBlock([FollowUpItem("追问一")])])`}
        onContinueConversation={onContinueConversation}
      />,
    )

    await userEvent.click(await screen.findByRole('button', { name: '追问一' }))

    expect(onContinueConversation).toHaveBeenCalledWith('追问一')
  })

  it('P2.1 展示组件按约定契约渲染', async () => {
    envMock.openUiEnabled = true
    render(<OpenUiRenderer response={DISPLAY_RESPONSE} />)

    expect(await screen.findByRole('img')).toHaveAttribute('src', 'https://example.com/cover.png')
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '40')
    expect(screen.getByText('处理中')).toBeInTheDocument()
    expect(screen.getByText('转化率')).toBeInTheDocument()
    expect(screen.getByText('订单数')).toBeInTheDocument()
    expect(screen.getByText('创建订单')).toBeInTheDocument()
    expect(screen.getByText('仓库出库')).toBeInTheDocument()
  })

  it('非 http/https 图片地址不渲染', async () => {
    envMock.openUiEnabled = true
    render(<OpenUiRenderer response={`root = Stack([Text("占位"), Image("javascript:alert(1)")])`} />)

    await screen.findByText('占位')

    expect(document.querySelector('img')).toBeNull()
  })

  it('P2.2 表单组件按约定契约渲染', async () => {
    envMock.openUiEnabled = true
    render(<OpenUiRenderer response={FORM_RESPONSE} />)

    expect(await screen.findByLabelText('姓名')).toBeInTheDocument()
    expect(screen.getByText('年龄')).toBeInTheDocument()
    expect(screen.getByText('套餐')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: '导出' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: '快速' })).toBeInTheDocument()
    expect(screen.getByRole('combobox')).toBeInTheDocument()
  })

  it('表单提交通过 onSubmitForm 回传全部字段值', async () => {
    envMock.openUiEnabled = true
    const onSubmitForm = vi.fn()
    render(<OpenUiRenderer response={FORM_RESPONSE} onSubmitForm={onSubmitForm} />)

    await userEvent.type(await screen.findByLabelText('姓名'), '张三')
    await userEvent.click(screen.getByRole('checkbox', { name: '导出' }))
    await userEvent.click(screen.getByRole('radio', { name: '快速' }))
    await userEvent.click(screen.getByRole('button', { name: '提交' }))

    expect(onSubmitForm).toHaveBeenCalledTimes(1)
    expect(onSubmitForm).toHaveBeenCalledWith(
      expect.objectContaining({
        formName: 'contact',
        fields: expect.objectContaining({
          name: '张三',
          features: ['export'],
          speed: 'fast',
        }),
      }),
    )
  })

  it('未提供 onSubmitForm 时表单字段并入继续对话消息', async () => {
    envMock.openUiEnabled = true
    const onContinueConversation = vi.fn()
    render(<OpenUiRenderer response={FORM_RESPONSE} onContinueConversation={onContinueConversation} />)

    await userEvent.type(await screen.findByLabelText('姓名'), '张三')
    await userEvent.click(screen.getByRole('button', { name: '提交' }))

    expect(onContinueConversation).toHaveBeenCalledTimes(1)
    expect(onContinueConversation.mock.calls[0]?.[0]).toContain('- name: 张三')
  })

  it('流式期间表单输入与按钮全部禁用', async () => {
    envMock.openUiEnabled = true
    render(<OpenUiRenderer response={FORM_RESPONSE} isStreaming onContinueConversation={vi.fn()} />)

    expect(await screen.findByLabelText('姓名')).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: '导出' })).toBeDisabled()
    expect(screen.getByRole('radio', { name: '快速' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '提交' })).toBeDisabled()
  })

  it('confirm 按钮首次点击只进入确认态，第二次才触发动作', async () => {
    envMock.openUiEnabled = true
    const onContinueConversation = vi.fn()
    render(
      <OpenUiRenderer
        response={`root = Stack([Button("删除", @ToAssistant("确认删除"), "outline", true)])`}
        onContinueConversation={onContinueConversation}
      />,
    )

    await userEvent.click(await screen.findByRole('button', { name: '删除' }))

    expect(onContinueConversation).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: '再次点击确认' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '再次点击确认' }))

    expect(onContinueConversation).toHaveBeenCalledWith('确认删除')
  })
})
