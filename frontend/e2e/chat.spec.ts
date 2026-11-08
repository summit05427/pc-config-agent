import { expect, test, type Page } from '@playwright/test'

import {
  mockChatBackend,
  startSseServer,
  type HistoryMessage,
  type SseServerHandle,
} from './support/chat-harness'

let sseServer: SseServerHandle

const USER_QUESTION = '问题'
const FULL_ANSWER = '你好，世界'

/** done 之后服务端返回的历史按 desc 顺序，页面会反转成时间正序 */
const persistedHistory: HistoryMessage[] = [
  { role: 'assistant', content: FULL_ANSWER },
  { role: 'user', content: USER_QUESTION },
]

const openNewChat = async (page: Page): Promise<void> => {
  await page.goto('/chat/new')
  // 新会话入口会被规范化成带 UUID 的地址，保证可刷新、可分享
  await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}/)
}

const sendMessage = async (page: Page, text: string): Promise<void> => {
  const composer = page.getByLabel('消息输入框')
  await composer.fill(text)
  await composer.press('Enter')
}

test.beforeAll(async () => {
  sseServer = await startSseServer()
})

test.afterAll(async () => {
  await sseServer.close()
})

test('token 流逐段渲染直至 done @critical', async ({ page }) => {
  await mockChatBackend(page, {
    sseUrl: sseServer.url,
    scenario: 'token',
    history: persistedHistory,
  })

  await openNewChat(page)
  await sendMessage(page, USER_QUESTION)

  const assistant = page.locator('[data-message-role="assistant"]')
  await expect(assistant).toContainText('你好')
  // 第二段 token 仍在延迟中：能看到第一段而看不到第二段，才证明是逐段渲染
  await expect(assistant).not.toContainText('，世界')
  await expect(assistant).toContainText(FULL_ANSWER)
  await expect(page.getByRole('button', { name: '发送' })).toBeVisible()
})

test('tool_call 与 tool_result 在同一轨迹内关联 @critical', async ({ page }) => {
  const history: HistoryMessage[] = [
    { role: 'assistant', content: '检索完成，这是结论。' },
    { role: 'tool', name: 'search', content: '检索完成' },
    {
      role: 'assistant',
      content: '先检索一下。',
      tool_calls: [{ name: 'search', args: { query: 'agent' } }],
    },
    { role: 'user', content: USER_QUESTION },
  ]

  await mockChatBackend(page, { sseUrl: sseServer.url, scenario: 'tools', history })

  await openNewChat(page)
  await sendMessage(page, USER_QUESTION)

  const assistant = page.locator('[data-message-role="assistant"]').first()
  await expect(assistant.getByText('执行轨迹')).toBeVisible()
  await expect(assistant.getByRole('button', { name: /search/ })).toBeVisible()
  await expect(assistant.getByText('已完成')).toBeVisible()
  await expect(assistant.getByText(/\d+ms/)).toBeVisible()

  // 结果必须挂在同名步骤上，而不是一条孤立记录
  await assistant.getByRole('button', { name: /search/ }).click()
  await expect(assistant.getByText('{"query":"agent"}')).toBeVisible()
  await expect(assistant.getByText('检索完成', { exact: true })).toBeVisible()
})

test('done 之后重新同步历史且消息不重复 @critical', async ({ page }) => {
  const backend = await mockChatBackend(page, {
    sseUrl: sseServer.url,
    scenario: 'token',
    history: persistedHistory,
  })

  await openNewChat(page)
  // 草稿会话在服务端还没有记录，首屏不应查询历史
  expect(backend.messageRequests).toBe(0)

  await sendMessage(page, USER_QUESTION)

  const assistant = page.locator('[data-message-role="assistant"]')
  await expect(assistant).toContainText(FULL_ANSWER)
  await expect(page.getByRole('button', { name: '发送' })).toBeVisible()

  // 交接后历史替换了临时消息，同一段问答只应有一条
  await expect(assistant).toHaveCount(1)
  await expect(page.locator('[data-message-role="user"]')).toHaveCount(1)

  // 落库确认 + 失效后的重新拉取；草稿首屏不再产生一次必然 404 的查询
  expect(backend.messageRequests).toBeGreaterThanOrEqual(2)
})

test('error 事件展示错误条并保留已生成内容 @critical', async ({ page }) => {
  await mockChatBackend(page, { sseUrl: sseServer.url, scenario: 'error' })

  await openNewChat(page)
  await sendMessage(page, USER_QUESTION)

  const assistant = page.locator('[data-message-role="assistant"]')
  await expect(assistant).toContainText('已生成部分内容')

  const notice = page.getByRole('alert')
  await expect(notice).toContainText('模型服务不可用')
  await expect(notice.getByRole('button', { name: '重试' })).toBeVisible()

  // 错误只影响状态与提示，已经生成的内容不能被清空
  await expect(assistant).toContainText('已生成部分内容')
})

test('停止生成中断流并保留已生成内容 @critical', async ({ page }) => {
  await mockChatBackend(page, { sseUrl: sseServer.url, scenario: 'stop' })

  await openNewChat(page)
  await sendMessage(page, USER_QUESTION)

  const assistant = page.locator('[data-message-role="assistant"]')
  await expect(assistant).toContainText('已生成内容')

  await page.getByRole('button', { name: '停止生成' }).click()

  await expect(page.getByText('生成已停止，你仍然可以重试这次提问。')).toBeVisible()
  await expect(page.getByRole('button', { name: '发送' })).toBeVisible()

  // 中止后不再追加 token：跨过一个产出周期后内容保持不变
  const cancelledText = await assistant.innerText()
  await page.waitForTimeout(300)
  expect(await assistant.innerText()).toBe(cancelledText)
})

test('带 sessionId 的深层链接刷新后历史顺序与内容正确 @critical', async ({ page }) => {
  const history: HistoryMessage[] = [
    { role: 'assistant', content: '第二轮的答复' },
    { role: 'user', content: '第二个问题' },
    { role: 'assistant', content: '第一轮的答复' },
    { role: 'user', content: '第一个问题' },
  ]

  await mockChatBackend(page, {
    sseUrl: sseServer.url,
    scenario: 'token',
    isPersistedInitially: true,
    history,
  })

  await page.goto('/chat/session-deep')

  const items = page.locator('[data-message-role]')
  await expect(items).toHaveCount(4)
  await expect(items.nth(0)).toContainText('第一个问题')
  await expect(items.nth(1)).toContainText('第一轮的答复')
  await expect(items.nth(2)).toContainText('第二个问题')
  await expect(items.nth(3)).toContainText('第二轮的答复')

  await page.reload()

  await expect(items).toHaveCount(4)
  await expect(items.nth(0)).toContainText('第一个问题')
  await expect(items.nth(1)).toContainText('第一轮的答复')
  await expect(items.nth(2)).toContainText('第二个问题')
  await expect(items.nth(3)).toContainText('第二轮的答复')
})
