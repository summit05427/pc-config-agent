import { expect, test } from '@playwright/test'

import {
  mockChatBackend,
  startSseServer,
  type HistoryMessage,
  type SessionSummary,
  type SseServerHandle,
} from './support/chat-harness'

let sseServer: SseServerHandle

// 侧栏两条会话，切换目标固定为 B，断言时用标题定位侧栏条目
const SESSION_A: SessionSummary = {
  thread_id: 'session-a',
  title: '会话 A',
  model_key: null,
  last_active_at: '2026-10-01T08:00:00Z',
}
const SESSION_B: SessionSummary = {
  thread_id: 'session-b',
  title: '会话 B',
  model_key: null,
  last_active_at: '2026-09-30T08:00:00Z',
}

/** 服务端按 desc 顺序返回，页面反转后按时间正序渲染 */
const HISTORY_A: HistoryMessage[] = [
  { role: 'assistant', content: 'A 的历史答复' },
  { role: 'user', content: 'A 的历史提问' },
]
const HISTORY_B: HistoryMessage[] = [
  { role: 'assistant', content: 'B 的历史答复' },
  { role: 'user', content: 'B 的历史提问' },
]

/** 观察窗口要大于流式产出间隔，才能确认切换后内容不再追加 */
const GROWTH_WINDOW_MS = 300
/** stop 场景本身持续约 3 秒，1.5 秒内看到断开只可能是 abort */
const ABORT_TIMEOUT_MS = 1500

test.beforeAll(async () => {
  sseServer = await startSseServer()
})

test.afterAll(async () => {
  await sseServer.close()
})

test('切换会话中止在途流并展示目标会话历史 @critical', async ({ page }) => {
  await mockChatBackend(page, {
    sseUrl: sseServer.url,
    scenario: 'stop',
    sessions: [SESSION_A, SESSION_B],
    histories: { 'session-a': HISTORY_A, 'session-b': HISTORY_B },
  })

  await page.goto('/chat/session-a')

  const main = page.getByRole('main')
  await expect(main.getByText('A 的历史提问', { exact: true })).toBeVisible()

  const composer = page.getByLabel('消息输入框')
  await composer.fill('切换期间的新问题')
  await composer.press('Enter')

  // 流已开始且仍在产出，此时切换会话才具备中断在途流的前提
  const assistant = page.locator('[data-message-role="assistant"]').last()
  await expect(assistant).toContainText('已生成内容')

  const streamingText = await assistant.innerText()
  expect(streamingText.length).toBeGreaterThan(0)

  await page.getByRole('button', { name: /会话 B/ }).click()

  await expect(page).toHaveURL(/\/chat\/session-b$/)
  await expect(main.getByText('B 的历史提问', { exact: true })).toBeVisible()

  // a 的流式内容不能残留到目标会话
  await expect(main.getByText('已生成内容')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '发送' })).toBeVisible()

  // 后端连接被关闭：只有 abort 才会让仍在产出的 stop 场景提前断开
  await expect
    .poll(() => sseServer.abortedThreadIds, { timeout: ABORT_TIMEOUT_MS })
    .toContain('session-a')

  // 内容不再增长：跨过流式产出间隔后主区域文本必须完全不变
  const settledText = await main.innerText()
  await page.waitForTimeout(GROWTH_WINDOW_MS)
  expect(await main.innerText()).toBe(settledText)
})
