/**
 * 真实场景剧本夹具。
 *
 * 与 `component-fixtures.ts` 的分工：那边每个夹具只验证一组组件的渲染契约；
 * 这里模拟模型在真实对话中会产出的完整回答（行程、报销表单、商品对比），
 * 用来覆盖组件组合、长内容与表格分页，同时作为 `/dev/openui` 的人工验收样例。
 *
 * 约束与组件夹具一致：`dsl` 必须是完整程序，所有变量都能从 root 到达。
 */
export interface ScenarioFixture {
  /** 剧本名称，也是 gallery 的分组标题 */
  name: string
  /** 模拟的用户提问，便于在 gallery 中理解这个剧本要解决什么 */
  prompt: string
  /** 完整 openui-lang 程序 */
  dsl: string
  /** 至少出现一次的可见文本；第一项用于等待渲染完成 */
  expectText: readonly string[]
}

/** 杭州一日游：卡片 + 指标 + 标签页 + 时间线 + 追问的组合回答 */
export const HANGZHOU_TRIP_SCENARIO: ScenarioFixture = {
  name: '杭州一日游',
  prompt: '帮我安排杭州一日游，包含路线、餐饮和注意事项',
  dsl: `
root = Stack([summary, tabs, followUps], "vertical", "md")
summary = Card([metrics], "杭州一日游", "西湖 + 灵隐寺，步行与地铁为主")
metrics = Stack([budget, walking], "horizontal", "sm")
budget = MetricCard("人均预算", "¥ 320", "+12%", "up", "含门票与餐饮")
walking = MetricCard("步行距离", "6.4 km", "-8%", "down", "较常规路线更省力")
tabs = Tabs([routeTab, foodTab, tipsTab])
routeTab = TabItem("route", "路线", [routeText, spots])
routeText = Text("上午西湖，下午灵隐，傍晚河坊街。", "body")
spots = Timeline([spotWest, spotTemple, spotStreet])
spotWest = TimelineItem("09:00 西湖", "断桥残雪 → 白堤 → 平湖秋月")
spotTemple = TimelineItem("13:30 灵隐寺", "飞来峰造像与永福寺")
spotStreet = TimelineItem("17:30 河坊街", "小吃与伴手礼")
foodTab = TabItem("food", "餐饮", [foodText])
foodText = Text("推荐知味观小笼与楼外楼西湖醋鱼，人均 80 元。", "body")
tipsTab = TabItem("tips", "贴士", [tips])
tips = Accordion([tipTicket, tipWeather])
tipTicket = AccordionItem("ticket", "门票", [ticketText])
tipWeather = AccordionItem("weather", "天气", [weatherText])
ticketText = Text("灵隐寺飞来峰景区需单独购票，建议提前预约。")
weatherText = Text("春秋季多雨，随身带折叠伞。")
followUps = FollowUpBlock([askTicket, askFamily])
askTicket = FollowUpItem("帮我查一下灵隐寺的门票价格")
askFamily = FollowUpItem("换成亲子路线怎么安排？")
`.trim(),
  expectText: ['杭州一日游', '人均预算', '¥ 320', '上午西湖，下午灵隐，傍晚河坊街。'],
}

/** 报销申请：覆盖全部输入组件，提交时回传完整字段值 */
export const REIMBURSEMENT_SCENARIO: ScenarioFixture = {
  name: '报销申请',
  prompt: '我要提交一笔差旅报销，需要填写哪些信息？',
  dsl: `
root = Stack([intro, form], "vertical", "md")
intro = Text("请核对报销信息，提交后由财务复核。", "body")
form = Form("reimbursement-2026-11", submit, [applicant, amount, category, invoiceNo, attachments, urgency, remark])
submit = Button("提交报销")
applicant = TextInput("applicant", "申请人", "请输入姓名", "张三", "与工号绑定的姓名")
amount = NumberInput("amount", "报销金额", "0.00", 320, 0, 100000, 0.01, "单笔不超过 10 万元")
category = Select("category", "费用类型", [travel, meal, office], "请选择", "travel", "用于财务分类统计")
invoiceNo = TextInput("invoiceNo", "发票号", "请输入发票号", "", "增值税发票 20 位号码")
attachments = CheckboxGroup("attachments", "附件", [invoice, receipt, approval], ["invoice"], "至少上传发票")
urgency = RadioGroup("urgency", "紧急程度", [normal, urgent], "normal", "加急需部门负责人审批")
remark = TextInput("remark", "备注", "补充说明（可选）")
travel = SelectOption("travel", "差旅")
meal = SelectOption("meal", "餐饮")
office = SelectOption("office", "办公用品")
invoice = CheckboxOption("invoice", "发票")
receipt = CheckboxOption("receipt", "收据")
approval = CheckboxOption("approval", "审批单")
normal = RadioOption("normal", "普通")
urgent = RadioOption("urgent", "加急")
`.trim(),
  expectText: [
    '请核对报销信息，提交后由财务复核。',
    '申请人',
    '报销金额',
    '费用类型',
    '发票号',
    '附件',
    '紧急程度',
    '备注',
    '提交报销',
  ],
}

interface PhoneRow {
  model: string
  price: number
  battery: string
  audience: string
}

/**
 * 14 款机型：超过 10 行会触发表格分页；最后一行文案刻意写长，
 * 用来验证单元格换行与横向滚动不会撑破消息宽度。
 */
const PHONE_ROWS: readonly PhoneRow[] = [
  { model: 'iPhone 16', price: 5999, battery: '视频 22 小时', audience: 'iOS 生态与长期系统更新' },
  {
    model: 'iPhone 16 Pro',
    price: 7999,
    battery: '视频 27 小时',
    audience: '影像创作与高帧率游戏',
  },
  {
    model: '华为 Mate 70',
    price: 5499,
    battery: '视频 20 小时',
    audience: '商务办公与信号稳定性',
  },
  { model: '华为 Pura 70', price: 5499, battery: '视频 18 小时', audience: '人像摄影' },
  { model: '小米 15', price: 4499, battery: '视频 21 小时', audience: '小屏旗舰与性能释放' },
  { model: '小米 15 Pro', price: 5299, battery: '视频 24 小时', audience: '长续航与大屏影音' },
  { model: 'OPPO Find X8', price: 4199, battery: '视频 19 小时', audience: '轻薄手感与快充' },
  { model: 'vivo X200', price: 4299, battery: '视频 20 小时', audience: '演唱会与远摄' },
  { model: '荣耀 Magic7', price: 4499, battery: '视频 23 小时', audience: '护眼屏与 AI 助手' },
  { model: '一加 13', price: 4499, battery: '视频 25 小时', audience: '高刷游戏与散热' },
  { model: 'realme GT7 Pro', price: 3599, battery: '视频 26 小时', audience: '性价比与超长续航' },
  { model: 'Redmi K80', price: 2499, battery: '视频 24 小时', audience: '预算有限的性能党' },
  { model: 'iQOO Neo10', price: 2299, battery: '视频 20 小时', audience: '电竞与快充' },
  {
    model: '三星 Galaxy S24',
    price: 4999,
    battery: '视频 19 小时',
    audience:
      '需要长焦与手写笔生态，同时希望机身足够轻便、系统更新周期长，并且经常在户外强光下使用',
  },
]

/** 用 JSON 数组字面量拼装数据列，避免手写 14 行时列长度不一致 */
const toLangArray = (values: readonly (string | number | boolean)[]): string =>
  JSON.stringify(values)

const PHONE_COMPARISON_DSL = [
  'root = Stack([intro, table, followUps], "vertical", "md")',
  'intro = Text("按预算与使用场景整理了 14 款机型，价格为首发价。", "body")',
  'table = Table([model, price, battery, audience])',
  `model = Col("机型", ${toLangArray(PHONE_ROWS.map((row) => row.model))})`,
  `price = Col("价格（元）", ${toLangArray(PHONE_ROWS.map((row) => row.price))})`,
  `battery = Col("续航", ${toLangArray(PHONE_ROWS.map((row) => row.battery))})`,
  `audience = Col("适合人群", ${toLangArray(PHONE_ROWS.map((row) => row.audience))})`,
  'followUps = FollowUpBlock([askBattery, askBudget])',
  'askBattery = FollowUpItem("把续航最强的三款单独列出来")',
  'askBudget = FollowUpItem("预算 4000 元以内怎么选？")',
].join('\n')

/** 商品对比表：长表分页 + 长文本单元格 */
export const PHONE_COMPARISON_SCENARIO: ScenarioFixture = {
  name: '手机对比表',
  prompt: '对比一下 2026 年主流旗舰手机的价格和续航',
  dsl: PHONE_COMPARISON_DSL,
  expectText: [
    '按预算与使用场景整理了 14 款机型，价格为首发价。',
    '机型',
    'iPhone 16',
    '价格（元）',
  ],
}

export const SCENARIO_FIXTURES: readonly ScenarioFixture[] = [
  HANGZHOU_TRIP_SCENARIO,
  REIMBURSEMENT_SCENARIO,
  PHONE_COMPARISON_SCENARIO,
]
