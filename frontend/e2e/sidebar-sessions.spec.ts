import { expect, test, type Page, type Route } from '@playwright/test'

const API_PATTERN = '**/api/v*/**'
const DEFAULT_ORIGIN = 'http://localhost:5273'
const TOTAL = 25
const PAGE_SIZE = 20

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

const pathOf = (route: Route): string => new URL(route.request().url()).pathname

// 标题带序号，便于用可见文本直接判断当前展示的是第几页
const allSessions = Array.from({ length: TOTAL }, (_, index) => ({
  thread_id: `session-${index + 1}`,
  title: `会话 ${String(index + 1).padStart(2, '0')}`,
  model_key: null,
  last_active_at: '2026-10-01T08:00:00Z',
}))

const fulfillSessions = async (route: Route): Promise<void> => {
  const url = new URL(route.request().url())
  const page = Number(url.searchParams.get('page') ?? '1')
  const size = Number(url.searchParams.get('size') ?? String(PAGE_SIZE))
  const offset = (page - 1) * size

  return fulfillJson(route, {
    list: allSessions.slice(offset, offset + size),
    total: TOTAL,
    page,
    size,
  })
}

const mockBackend = async (page: Page): Promise<void> => {
  await page.route(API_PATTERN, async (route) => {
    if (route.request().method() === 'OPTIONS') {
      return fulfillPreflight(route)
    }

    const path = pathOf(route)

    // 本地绝对地址没有 /agent 代理前缀，按业务路径段匹配两者
    if (path.includes('/api/v1/sessions')) {
      return fulfillSessions(route)
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

test('侧栏最近会话只展示第一页 @critical', async ({ page }) => {
  await mockBackend(page)

  // 历史页已移除，会话入口收敛到侧栏「最近」区块
  await page.goto('/chat/new')
  await expect(page.getByRole('button', { name: '收起最近会话' })).toBeVisible()

  const sidebar = page.locator('aside')

  await expect(sidebar.getByText('会话 01', { exact: true })).toBeVisible()
  await expect(sidebar.getByText('会话 21', { exact: true })).toHaveCount(0)
  // 侧栏固定只取第一页，不再提供翻页控件
  await expect(page.getByRole('button', { name: '下一页' })).toHaveCount(0)

  await sidebar.getByText('会话 01', { exact: true }).click()
  await expect(page).toHaveURL(/\/chat\/session-1$/)
})
