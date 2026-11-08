import { expect, test, type Page, type Route } from '@playwright/test'

const API_PATTERN = '**/api/v*/**'
const DEFAULT_ORIGIN = 'http://localhost:5273'

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

const loginPayload = {
  accessToken: 'e2e-token',
  tokenType: 'Bearer',
  expiresIn: 900,
  user: currentUser,
}

/** Agent 返回裸 JSON，不使用 Java 信封 */
const emptySessions = { list: [], total: 0, page: 1, size: 20 }

const pathOf = (route: Route): string => new URL(route.request().url()).pathname

/**
 * 统一的登录态 mock：未登录时刷新失败，登录成功后用户资料与空会话列表可用。
 * 所有请求走 page.route，不依赖真实后端。
 */
const mockAuthBackend = async (page: Page): Promise<void> => {
  await page.route(API_PATTERN, async (route) => {
    if (route.request().method() === 'OPTIONS') {
      return fulfillPreflight(route)
    }

    const path = pathOf(route)

    if (path.includes('/agent/api/v1/sessions')) {
      return fulfillJson(route, emptySessions)
    }
    if (path.endsWith('/auth/refresh')) {
      // 未登录时 Cookie 不存在，刷新必须失败，让守卫跳到登录页
      return fulfillJson(route, { code: 40101, message: '未登录' }, 401)
    }
    if (path.endsWith('/auth/login')) {
      return fulfillJson(route, envelope(loginPayload))
    }
    if (path.endsWith('/auth/me')) {
      return fulfillJson(route, envelope(currentUser))
    }

    return fulfillJson(route, { code: 40401, message: '未 mock 的接口' }, 404)
  })
}

const signIn = async (page: Page): Promise<void> => {
  // 密码框旁边有「显示密码」按钮，label 必须精确匹配才不会同时命中该按钮
  await page.getByLabel('用户名', { exact: true }).fill('tester')
  await page.getByLabel('密码', { exact: true }).fill('secret')
  await page.getByRole('button', { name: '登录' }).click()
}

test('未登录登录后进入新对话 @critical', async ({ page }) => {
  await mockAuthBackend(page)

  await page.goto('/login')
  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible()
  expect(new URL(page.url()).searchParams.get('redirect')).toBeNull()

  await signIn(page)

  await expect(page).toHaveURL(/\/chat\/[^/]+$/)
  await expect(page.getByRole('button', { name: '收起最近会话' })).toBeVisible()
})

test('登录后回跳 redirect 指定的原路径 @critical', async ({ page }) => {
  await mockAuthBackend(page)

  await page.goto('/settings/general')
  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible()

  const redirectParam = new URL(page.url()).searchParams.get('redirect')
  expect(redirectParam).toBe('/settings/general')

  await signIn(page)

  await expect(page).toHaveURL(/\/settings\/general$/)
  await expect(page.getByRole('heading', { name: '常规' })).toBeVisible()
})
