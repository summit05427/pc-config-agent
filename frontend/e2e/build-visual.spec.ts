import { expect, test, type Page } from '@playwright/test'

import { mockChatBackend, startSseServer, type SseServerHandle } from './support/chat-harness'

/**
 * P1-03 前端视觉验收：八件配置、演示价提示、无解回退与 HITL 表单。
 *
 * 断言只依赖用户可见文案与结构，截图落在 `e2e/__screenshots__/`（已 gitignore），
 * 供人工复核版式；判定标准是断言，不是截图。
 */

let sseServer: SseServerHandle

const CATEGORY_LABELS = ['CPU', '主板', '内存', '显卡', '电源', '机箱', '散热器', '硬盘']
const MODEL_NAMES = [
  'Intel Core i5-14600KF',
  '微星 B760M MORTAR WIFI',
  '金士顿 FURY 16GB×2 DDR5-6000',
  '影驰 RTX 4070 SUPER 金属大师',
  '振华 LEADEX III 750W',
  '酷冷至尊 MB520',
  '利民 PA120 SE',
  '致钛 TiPlus7100 1TB',
]

const openNewChat = async (page: Page): Promise<void> => {
  await page.goto('/chat/new')
  await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}/)
}

const sendMessage = async (page: Page, text: string): Promise<void> => {
  const composer = page.getByLabel('消息输入框')
  await composer.fill(text)
  await composer.press('Enter')
}

/** 截图留档；失败也不影响断言结果，因此只作为附属产物 */
const capture = async (page: Page, name: string): Promise<void> => {
  await page.screenshot({ path: `e2e/__screenshots__/${name}.png`, fullPage: true })
}

test.beforeAll(async () => {
  sseServer = await startSseServer()
})

test.afterAll(async () => {
  await sseServer.close()
})

test('八件配置齐全且演示价显著标注 @critical', async ({ page }) => {
  // histories 传空对象：会话永远 404，页面保留流式产出的结构化结果，不被历史回放覆盖
  await mockChatBackend(page, {
    sseUrl: sseServer.url,
    scenario: 'build',
    histories: {},
  })

  await openNewChat(page)
  await sendMessage(page, '预算 12000 元，主要打游戏')

  const card = page.getByTestId('build-result-card')
  await expect(card).toBeVisible()

  // 八件硬件各一行；top ul 是硬件清单，兼容性清单在下方另一个 ul
  const rows = card.locator('ul').first().locator('li')
  await expect(rows).toHaveCount(8)
  // 类别中文名与具体型号成对出现，漏翻译或串行都会在这里暴露
  for (const [index, model] of MODEL_NAMES.entries()) {
    await expect(rows.filter({ hasText: model })).toContainText(CATEGORY_LABELS[index] ?? '')
  }

  // 演示价必须同时出现在顶部横幅与具体行上，不能只在底部免责声明里提一句
  await expect(card.getByText('演示价格，非真实在售', { exact: true })).toBeVisible()
  await expect(card.getByText('演示价', { exact: true })).toHaveCount(2)

  // 总价与预算徽标按整数分渲染，便于人工核对八件是否漏项
  await expect(card.getByText('¥10,592.00', { exact: true })).toBeVisible()
  await expect(card.getByText('预算内', { exact: true })).toBeVisible()
  await expect(card.getByText('性能分配说明', { exact: true })).toBeVisible()
  // 理由按 hardware_id 关联到具体行，不能只挂在卡片底部
  await expect(card.getByText('游戏用途下显卡决定帧率，4070 SUPER 在两万元内性价比最高。')).toBeVisible()

  await capture(page, 'build-eight-components')
})

test('无解回退不渲染配置卡片 @critical', async ({ page }) => {
  await mockChatBackend(page, {
    sseUrl: sseServer.url,
    scenario: 'no-solution',
    histories: {},
  })

  await openNewChat(page)
  await sendMessage(page, '预算 8000 元，主要打游戏')

  const assistant = page.locator('[data-message-role="assistant"]')
  await expect(assistant).toContainText('没有可行方案')
  await expect(assistant).toContainText('¥10,592.00')
  // 无解时绝不能出现半成品卡片：那等于给了不存在价格的方案
  await expect(page.getByTestId('build-result-card')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '发送' })).toBeVisible()

  await capture(page, 'no-solution-fallback')
})

test('澄清中断渲染表单并在提交后消失 @critical', async ({ page }) => {
  const streamBodies: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/chat/stream')) {
      streamBodies.push(request.postData() ?? '')
    }
  })

  await mockChatBackend(page, {
    sseUrl: sseServer.url,
    scenario: 'hitl',
    histories: {},
  })

  await openNewChat(page)
  await sendMessage(page, '帮我配台电脑')

  await expect(page.getByText('还差两个信息才能求解，补齐后我继续。')).toBeVisible()
  await expect(page.getByLabel('预算（元）')).toBeVisible()
  await expect(page.getByLabel('主要用途')).toBeVisible()

  // 必填项为空时本地拦截，不应发出第二个请求
  await page.getByRole('button', { name: '提交并继续' }).click()
  await expect(page.getByRole('alert')).toHaveText('请填写必填项')
  expect(streamBodies).toHaveLength(1)

  await capture(page, 'hitl-clarify-form')

  await page.getByLabel('预算（元）').fill('8000')
  await page.getByLabel('主要用途').selectOption('GAMING')
  await page.getByRole('button', { name: '提交并继续' }).click()

  await expect(page.getByText('收到，按 8000 元游戏用途继续求解。')).toBeVisible()
  // 已作答的表单必须消失，否则用户会以为还能改答案并重复提交同一个中断
  await expect(page.getByRole('button', { name: '提交并继续' })).toHaveCount(0)

  expect(streamBodies).toHaveLength(2)
  const resumePayload = JSON.parse(streamBodies[1] ?? '{}') as { resume?: unknown }
  expect(resumePayload.resume).toEqual({
    interrupt_id: 'int-e2e-clarify',
    answer: { budget_yuan: 8000, scenario: 'GAMING' },
  })

  await capture(page, 'hitl-resumed')
})
