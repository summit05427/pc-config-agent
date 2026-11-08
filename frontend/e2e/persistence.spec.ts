import { expect, test, type Page, type Route } from '@playwright/test'

const API_PATTERN = '**/api/v*/**'
const DEFAULT_ORIGIN = 'http://localhost:5273'
const APP_STATE_KEY = 'app-state'
// 与 AppPreferences 的全量字段一致，用于断言平铺结构完整
const EXPECTED_KEYS = [
  'fontScale',
  'isSidebarCollapsed',
  'locale',
  'showAccountMenuIcon',
  'showTimestamps',
  'sidebarWidth',
  'theme',
]

const corsHeaders = (route: Route): Record<string, string> => {
  const origin = route.request().headers()['origin'] ?? DEFAULT_ORIGIN

  return {
    'access-control-allow-origin': origin,
    'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
    'access-control-allow-headers': 'authorization,content-type,idempotency-key,x-request-id',
    'access-control-expose-headers': 'x-request-id',
  }
}

const fulfillPreflight = async (route: Route): Promise<void> => {
  await route.fulfill({ status: 204, headers: corsHeaders(route) })
}

const fulfillJson = async (route: Route, body: unknown, status = 200): Promise<void> => {
  await route.fulfill({
    status,
    headers: { ...corsHeaders(route), 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
}

const envelope = (data?: unknown): unknown => ({
  code: 0,
  data,
  message: 'ok',
  requestId: 'req-e2e',
})

const currentUser = {
  publicId: 'e2e-user',
  username: 'tester',
  roles: ['USER'],
}

const refreshPayload = {
  accessToken: 'refreshed-token',
  tokenType: 'Bearer',
  expiresIn: 900,
}

const emptySessions = { list: [], total: 0, page: 1, size: 20 }

const pathOf = (route: Route): string => new URL(route.request().url()).pathname

/**
 * 已登录场景 mock：刷新成功证明刷新令牌仍有效，刷新页面后应恢复登录态。
 */
const mockSessionBackend = async (page: Page): Promise<void> => {
  await page.route(API_PATTERN, async (route) => {
    if (route.request().method() === 'OPTIONS') {
      return fulfillPreflight(route)
    }

    const path = pathOf(route)

    if (path.includes('/agent/api/v1/sessions')) {
      return fulfillJson(route, emptySessions)
    }
    if (path.endsWith('/auth/refresh')) {
      return fulfillJson(route, envelope(refreshPayload))
    }
    if (path.endsWith('/auth/me')) {
      return fulfillJson(route, envelope(currentUser))
    }

    return fulfillJson(route, { code: 40401, message: '未 mock 的接口' }, 404)
  })
}

/** e2e 的 tsconfig 只引入 Node 类型，这里给浏览器侧 localStorage 一个最小结构 */
interface BrowserStorage {
  getItem(key: string): string | null
}

/** 读取 `app-state` 原文，解析失败直接让用例失败，避免把空对象当合法结构 */
const readAppState = async (page: Page): Promise<Record<string, unknown>> => {
  const raw = await page.evaluate((key) => {
    const storage = (globalThis as unknown as { localStorage: BrowserStorage }).localStorage
    return storage.getItem(key)
  }, APP_STATE_KEY)

  expect(raw).not.toBeNull()
  return JSON.parse(raw ?? '{}') as Record<string, unknown>
}

const expectFlatPreferences = (stored: Record<string, unknown>): void => {
  expect(Object.keys(stored).sort()).toEqual(EXPECTED_KEYS)
  expect(stored.theme).toBe('dark')
  expect(stored.locale).toBe('en-US')
}

test('主题与语言偏好刷新后保持 @critical', async ({ page }) => {
  await mockSessionBackend(page)

  await page.goto('/')
  await expect(page.getByRole('link', { name: '开始新对话' })).toBeVisible()

  await page.getByRole('button', { name: '切换主题' }).click()
  await page.getByRole('menuitem', { name: '深色' }).click()
  await expect(page.locator('html')).toHaveClass(/dark/)

  await page.getByRole('button', { name: '切换语言' }).click()
  await page.getByRole('menuitem', { name: 'English' }).click()
  await expect(page.getByRole('link', { name: 'Start a new chat' })).toBeVisible()

  const storedBeforeReload = await readAppState(page)
  expectFlatPreferences(storedBeforeReload)

  await page.reload()

  // 偏好不依赖登录态，刷新后必须仍从 app-state 读回
  await expect(page.getByRole('link', { name: 'Start a new chat' })).toBeVisible()
  await expect(page.locator('html')).toHaveClass(/dark/)
  expectFlatPreferences(await readAppState(page))
})
