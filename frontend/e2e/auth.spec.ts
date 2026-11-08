import { expect, test, type Route } from '@playwright/test'

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

const refreshPayload = {
  accessToken: 'refreshed-token',
  tokenType: 'Bearer',
  expiresIn: 900,
}

const pathOf = (route: Route): string => new URL(route.request().url()).pathname

test('登录恢复回跳 @critical', async ({ page }) => {
  await page.route(API_PATTERN, async (route) => {
    if (route.request().method() === 'OPTIONS') {
      return fulfillPreflight(route)
    }

    const path = pathOf(route)

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

  await page.goto('/chat/new')

  await expect(page).toHaveURL(/\/login\?redirect=/)
  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible()

  const redirectParam = new URL(page.url()).searchParams.get('redirect')
  expect(redirectParam).toBe('/chat/new')

  await page.getByLabel('用户名').fill('tester')
  await page.getByLabel('密码', { exact: true }).fill('secret')
  await page.getByRole('button', { name: '登录' }).click()

  // 新对话页生成 threadId 后规范化为 /chat/<id>，不再有独立工作台页
  await expect(page).toHaveURL(/\/chat\/[^/]+$/)
  await expect(page.getByRole('button', { name: '收起最近会话' })).toBeVisible()
})

test('401 刷新重放 @critical', async ({ page }) => {
  let refreshCount = 0
  let meCalls = 0
  let hasLoggedIn = false

  await page.route(API_PATTERN, async (route) => {
    if (route.request().method() === 'OPTIONS') {
      return fulfillPreflight(route)
    }

    const path = pathOf(route)

    if (path.endsWith('/auth/refresh')) {
      refreshCount += 1
      return hasLoggedIn
        ? fulfillJson(route, envelope(refreshPayload))
        : fulfillJson(route, { code: 40101, message: '未登录' }, 401)
    }
    if (path.endsWith('/auth/login')) {
      hasLoggedIn = true
      // 登录前的启动恢复会消耗一次刷新，从登录成功起重新计数
      refreshCount = 0
      return fulfillJson(route, envelope(loginPayload))
    }
    if (path.endsWith('/auth/me')) {
      meCalls += 1
      return meCalls === 1
        ? fulfillJson(route, { code: 40101, message: 'Token 过期' }, 401)
        : fulfillJson(route, envelope(currentUser))
    }

    return fulfillJson(route, { code: 40401, message: '未 mock 的接口' }, 404)
  })

  await page.goto('/login')
  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible()

  await page.getByLabel('用户名').fill('tester')
  await page.getByLabel('密码', { exact: true }).fill('secret')
  await page.getByRole('button', { name: '登录' }).click()

  await expect(page).toHaveURL(/\/chat\/[^/]+$/)
  await expect(page.getByRole('button', { name: '收起最近会话' })).toBeVisible()

  // 首次 /auth/me 401 后只允许换一次 Token，并重放一次原请求
  await expect.poll(() => refreshCount).toBe(1)
  expect(meCalls).toBe(2)
})

test('深层路由重定向保留完整路径 @critical', async ({ page }) => {
  await page.route(API_PATTERN, async (route) => {
    if (route.request().method() === 'OPTIONS') {
      return fulfillPreflight(route)
    }

    const path = pathOf(route)

    if (path.endsWith('/auth/refresh')) {
      return fulfillJson(route, { code: 40101, message: '未登录' }, 401)
    }

    return fulfillJson(route, { code: 40401, message: '未 mock 的接口' }, 404)
  })

  const deepLink = '/settings/profile?tab=security#top'
  await page.goto(deepLink)

  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible()

  const redirectParam = new URL(page.url()).searchParams.get('redirect')
  expect(redirectParam).toBe(deepLink)
})
