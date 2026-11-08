/**
 * 生成式 UI 的组件测试夹具（单一事实来源）。
 *
 * 同一份清单同时驱动：
 * 1. `component-fixtures.spec.ts` 的覆盖率守卫（少一个注册组件就失败）
 * 2. `component-contract.spec.tsx` 的逐组件渲染断言
 * 3. `/dev/openui` gallery 的人工验收与后续截图基线
 *
 * 约束：每个 `dsl` 必须是完整程序（首行 `root = Stack(...)`），且所有变量都可达，
 * 否则解析器会静默丢弃未引用节点，测试就会假通过。
 */
export interface ComponentFixture {
  /** 夹具名称，也是 gallery 的分组标题 */
  name: string
  /** 该夹具覆盖的注册组件名，必须与 OPENUI_LIBRARY 完全一致 */
  covers: readonly string[]
  /** 完整 openui-lang 程序 */
  dsl: string
  /** 至少出现一次的可见文本；第一项用于等待渲染完成 */
  expectText: readonly string[]
  /** 无文本组件（Image / Progress）用可访问性角色断言 */
  expectRole?: { role: string; count?: number }
}

export const COMPONENT_FIXTURES: readonly ComponentFixture[] = [
  {
    name: 'Stack',
    covers: ['Stack'],
    dsl: `
root = Stack([left, right], "horizontal", "md", "center")
left = Text("左侧文本")
right = Text("右侧文本", "muted")
`.trim(),
    expectText: ['左侧文本', '右侧文本'],
  },
  {
    name: 'Text',
    covers: ['Text'],
    dsl: `
root = Stack([heading, body, muted, caption], "vertical", "sm")
heading = Text("标题示例", "heading")
body = Text("正文示例", "body")
muted = Text("弱化文本", "muted")
caption = Text("说明文本", "caption")
`.trim(),
    expectText: ['标题示例', '正文示例', '弱化文本', '说明文本'],
  },
  {
    name: 'Card',
    covers: ['Card'],
    dsl: `
root = Stack([card], "vertical", "md")
card = Card([body], "卡片标题", "卡片说明")
body = Text("卡片正文")
`.trim(),
    expectText: ['卡片标题', '卡片说明', '卡片正文'],
  },
  {
    name: 'Badge',
    covers: ['Badge'],
    dsl: `
root = Stack([neutral, success, warning, danger], "horizontal", "sm")
neutral = Badge("中性", "neutral")
success = Badge("成功", "success")
warning = Badge("警告", "warning")
danger = Badge("危险", "danger")
`.trim(),
    expectText: ['中性', '成功', '警告', '危险'],
  },
  {
    name: 'Divider',
    covers: ['Divider'],
    dsl: `
root = Stack([above, divider, below], "vertical", "sm")
above = Text("分隔线之上")
divider = Divider()
below = Text("分隔线之下")
`.trim(),
    expectText: ['分隔线之上', '分隔线之下'],
  },
  {
    name: 'MetricCard',
    covers: ['MetricCard'],
    dsl: `
root = Stack([budget], "vertical", "md")
budget = MetricCard("总预算", "¥ 800", "+8.2%", "up", "含交通与餐饮")
`.trim(),
    expectText: ['总预算', '¥ 800', '+8.2%', '含交通与餐饮'],
  },
  {
    name: 'Button',
    covers: ['Button'],
    dsl: `
root = Stack([nav, confirm], "horizontal", "sm")
nav = Button("查看详情", @OpenUrl("https://example.com"))
confirm = Button("删除", @ToAssistant("确认删除"), "outline", true, "再点一次确认")
`.trim(),
    expectText: ['查看详情', '删除'],
  },
  {
    name: 'ActionGroup',
    covers: ['ActionGroup'],
    dsl: `
root = Stack([group], "vertical", "md")
group = ActionGroup([chat, docs], "horizontal")
chat = Button("继续对话")
docs = Button("打开官网", @OpenUrl("https://example.com"))
`.trim(),
    expectText: ['继续对话', '打开官网'],
  },
  {
    name: 'Progress',
    covers: ['Progress'],
    dsl: `
root = Stack([uploading, completed], "vertical", "sm")
uploading = Progress(42, "上传进度")
completed = Progress(100)
`.trim(),
    expectText: ['上传进度'],
    expectRole: { role: 'progressbar', count: 2 },
  },
  {
    name: 'MetricIndicator',
    covers: ['MetricIndicator'],
    dsl: `
root = Stack([metric], "vertical", "sm")
metric = MetricIndicator("1,280", "较上月", "1,150", {direction: "up", value: 11.3}, "inline")
`.trim(),
    expectText: ['1,280', '较上月'],
  },
  {
    name: 'Image',
    covers: ['Image'],
    dsl: `
root = Stack([cover], "vertical", "sm")
cover = Image("https://example.com/cover.png", "示例封面", "16:9")
`.trim(),
    expectText: [],
    expectRole: { role: 'img', count: 1 },
  },
  {
    name: 'Tabs',
    covers: ['Tabs', 'TabItem'],
    dsl: `
root = Stack([tabs], "vertical", "md")
tabs = Tabs([overview, detail])
overview = TabItem("overview", "概览", [overviewText])
detail = TabItem("detail", "详情", [detailText])
overviewText = Text("概览内容")
detailText = Text("详情内容")
`.trim(),
    expectText: ['概览', '详情'],
  },
  {
    name: 'Accordion',
    covers: ['Accordion', 'AccordionItem'],
    dsl: `
root = Stack([accordion], "vertical", "md")
accordion = Accordion([first, second])
first = AccordionItem("first", "第一节", [firstText])
second = AccordionItem("second", "第二节", [secondText])
firstText = Text("第一节内容")
secondText = Text("第二节内容")
`.trim(),
    expectText: ['第一节', '第二节'],
  },
  {
    name: 'Table',
    covers: ['Table', 'Col'],
    dsl: `
root = Stack([prices], "vertical", "md")
prices = Table([model, price, battery])
model = Col("机型", ["iPhone 16", "华为 Mate 70", "小米 15"])
price = Col("价格", [5999, 5499, 4499])
battery = Col("续航", ["18 小时", "16 小时", "14 小时"])
`.trim(),
    expectText: ['机型', 'iPhone 16', '18 小时'],
  },
  {
    name: 'StatGroup',
    covers: ['StatGroup', 'StatItem'],
    dsl: `
root = Stack([stats], "vertical", "md")
stats = StatGroup([users, conversion])
users = StatItem("12.6 万", "月活跃用户", null, null, "inline")
conversion = StatItem("4.8%", "转化率", "5.1%", {direction: "down", value: 0.3}, "with-strikethrough")
`.trim(),
    expectText: ['12.6 万', '月活跃用户', '4.8%', '转化率'],
  },
  {
    name: 'Timeline',
    covers: ['Timeline', 'TimelineItem'],
    dsl: `
root = Stack([timeline], "vertical", "md")
timeline = Timeline([kickoff, build, release])
kickoff = TimelineItem("需求确认", "与业务方确认范围与验收标准")
build = TimelineItem("开发联调", "前后端按契约联调")
release = TimelineItem("上线验收", "灰度发布并观察指标")
`.trim(),
    expectText: ['需求确认', '开发联调', '上线验收'],
  },
  {
    name: 'FollowUpBlock',
    covers: ['FollowUpBlock', 'FollowUpItem'],
    dsl: `
root = Stack([followUps], "vertical", "sm")
followUps = FollowUpBlock([cost, schedule])
cost = FollowUpItem("这个方案的成本是多少？")
schedule = FollowUpItem("能给出实施排期吗？")
`.trim(),
    expectText: ['这个方案的成本是多少？', '能给出实施排期吗？'],
  },
  {
    name: 'Form',
    covers: [
      'Form',
      'TextInput',
      'NumberInput',
      'Select',
      'SelectOption',
      'CheckboxGroup',
      'CheckboxOption',
      'RadioGroup',
      'RadioOption',
    ],
    dsl: `
root = Stack([form], "vertical", "md")
form = Form("reimbursement", submit, [applicant, amount, category, attachments, urgency])
applicant = TextInput("applicant", "申请人", "请输入姓名", "张三", "报销人姓名")
amount = NumberInput("amount", "金额", "0.00", 100, 0, 100000, 0.01, "单笔不超过 10 万")
category = Select("category", "费用类型", [travel, meal], "请选择", "travel", "用于分类统计")
attachments = CheckboxGroup("attachments", "附件", [invoice, receipt], ["invoice"])
urgency = RadioGroup("urgency", "紧急程度", [normal, urgent], "normal")
travel = SelectOption("travel", "差旅")
meal = SelectOption("meal", "餐饮")
invoice = CheckboxOption("invoice", "发票")
receipt = CheckboxOption("receipt", "收据")
normal = RadioOption("normal", "普通")
urgent = RadioOption("urgent", "加急")
submit = Button("提交申请")
`.trim(),
    expectText: ['申请人', '金额', '费用类型', '附件', '紧急程度', '提交申请'],
  },
]
