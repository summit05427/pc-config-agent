import { expect, test, type Page, type Route } from '@playwright/test'

const API_PATTERN = '**/api/v*/**'
const DEFAULT_ORIGIN = 'http://localhost:5273'
const APP_STATE_KEY = 'app-state'
const AGENT_THREAD_KEY = 'agent-thread'
/** Vue 侧写入的会话镜像，React 回退时应当沿用 */
const VUE_THREAD_ID = 'vue-thread-001'
/** Vue 侧独有的额外字段，React 回写时不能丢 */
const VUE_ONLY_FIELD = 'someVueOnlyField'
const VUE_ONLY_VALUE = 'keep-me'

/** 与 Vue pinia-plugin-persistedstate 写入的结构一致：平铺，不带 { state, version } 包装 */
const VUE_APP_STATE = {
  theme: 'dark',
  locale: 'en-US',
  isSidebarCollapsed: true,
  sidebarWidth: 260,
  [VUE_ONLY_FIELD]: VUE_ONLY_VALUE,
}

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

const currentUser = { publicId: 'e2e-user', username: 'tester', roles: ['USER'] }
const refreshPayload = { accessToken: 'refreshed-token', tokenType: 'Bearer', expiresIn: 900 }
const emptySessions = { list: [], total: 0, page: 1, size: 20 }

const mockBackend = async (page: Page): Promise<void> => {
  await page.route(API_PATTERN, async (route) => {
    if (route.request().method() === 'OPTIONS') {
      return fulfillPreflight(route)
    }

    const path = new URL(route.request().url()).pathname

    if (path.endsWith('/auth/refresh')) {
      return fulfillJson(route, envelope(refreshPayload))
    }
    if (path.endsWith('/auth/me')) {
      return fulfillJson(route, envelope(currentUser))
    }
    if (path === '/api/v2/models') {
      return fulfillJson(route, envelope({ list: [], total: 0, page: 1, size: 100 }))
    }
    if (path === '/agent/api/v1/sessions') {
      return fulfillJson(route, emptySessions)
    }
    if (/^\/agent\/api\/v1\/sessions\/[^/]+\/messages$/.test(path)) {
      return fulfillJson(route, { code: 40402, message: '会话尚未落库' }, 404)
    }

    return fulfillJson(route, { code: 40401, message: '未 mock 的接口' }, 404)
  })
}

type StorageArea = 'localStorage' | 'sessionStorage'

/** e2e 的 tsconfig 只引入 Node 类型，这里给浏览器存储一个最小结构 */
const readStorageRaw = async (page: Page, area: StorageArea, key: string): Promise<string | null> =>
  page.evaluate(
    ({ targetArea, targetKey }) => {
      const scope = globalThis as unknown as Record<
        string,
        { getItem(storageKey: string): string | null }
      >
      return scope[targetArea].getItem(targetKey)
    },
    { targetArea: area, targetKey: key },
  )

/** 解析失败直接失败用例，避免把空对象当合法结构 */
const readAppState = async (page: Page): Promise<Record<string, unknown>> => {
  const raw = await readStorageRaw(page, 'localStorage', APP_STATE_KEY)
  expect(raw).not.toBeNull()
  return JSON.parse(raw ?? '{}') as Record<string, unknown>
}

/**
 * 注入 Vue 版本已经写入的持久化数据。
 * 只在键缺失时写入，这样页面内的刷新与跳转不会覆盖 React 之后回写的值。
 */
const seedVueStorage = async (page: Page): Promise<void> => {
  await page.addInitScript(
    (seed) => {
      const scope = globalThis as unknown as {
        localStorage: { getItem(key: string): string | null; setItem(key: string, value: string): void }
        sessionStorage: { getItem(key: string): string | null; setItem(key: string, value: string): void }
      }

      if (scope.localStorage.getItem(seed.appStateKey) === null) {
        scope.localStorage.setItem(seed.appStateKey, JSON.stringify(seed.appState))
      }
      if (scope.sessionStorage.getItem(seed.threadKey) === null) {
        scope.sessionStorage.setItem(seed.threadKey, JSON.stringify(seed.threadId))
      }
    },
    {
      appStateKey: APP_STATE_KEY,
      threadKey: AGENT_THREAD_KEY,
      appState: VUE_APP_STATE,
      threadId: VUE_THREAD_ID,
    },
  )
}

/** Vue 与 React 读的都是「首屏主题 + 语言 + 侧栏折叠」，统一在这里断言 */
const expectVuePreferencesApplied = async (page: Page): Promise<void> => {
  await expect(page.locator('html')).toHaveClass(/dark/)
  // 折叠态才有展开入口；展开态才有的收起按钮必须不存在
  await expect(page.locator('[data-sidebar-expand]')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Collapse sidebar' })).toHaveCount(0)
}

test('Vue 与 React 的持久化数据双向兼容 @critical', async ({ page }) => {
  await mockBackend(page)
  await seedVueStorage(page)

  // —— Vue → React 读取 ——
  // 用已有会话进入外壳：/chat/new 会重写 agent-thread 镜像，先保留 Vue 写入的值
  await page.goto('/chat/vue-thread-001')
  await expectVuePreferencesApplied(page)
  await page.reload()
  await expectVuePreferencesApplied(page)

  // URL 缺少有效会话 ID 时回退到 agent-thread 镜像，并转成规范地址
  await page.goto('/chat/%20')
  await expect(page).toHaveURL(/\/chat\/vue-thread-001$/)

  // —— React → Vue 回读 ——
  // 主题与语言入口在欢迎页，读取 localStorage 与是否处于外壳无关
  await page.goto('/')
  await page.getByRole('button', { name: 'Switch theme' }).click()
  await page.getByRole('menuitem', { name: 'Light' }).click()
  await expect(page.locator('html')).not.toHaveClass(/dark/)

  await page.getByRole('button', { name: 'Switch language' }).click()
  await page.getByRole('menuitem', { name: '简体中文' }).click()
  await expect(page.getByRole('link', { name: '开始新对话' })).toBeVisible()

  const storedPreferences = await readAppState(page)
  // 结构仍是平铺对象，Vue 独有字段没有被 React 覆盖
  expect(Object.keys(storedPreferences).sort()).toEqual([
    'fontScale',
    'isSidebarCollapsed',
    'locale',
    'showAccountMenuIcon',
    'showTimestamps',
    'sidebarWidth',
    VUE_ONLY_FIELD,
    'theme',
  ])
  expect(storedPreferences.theme).toBe('light')
  expect(typeof storedPreferences.theme).toBe('string')
  expect(storedPreferences.locale).toBe('zh-CN')
  expect(typeof storedPreferences.locale).toBe('string')
  expect(storedPreferences.isSidebarCollapsed).toBe(true)
  expect(typeof storedPreferences.isSidebarCollapsed).toBe('boolean')
  expect(storedPreferences.sidebarWidth).toBe(260)
  expect(typeof storedPreferences.sidebarWidth).toBe('number')
  expect(storedPreferences[VUE_ONLY_FIELD]).toBe(VUE_ONLY_VALUE)

  // 会话镜像仍是 JSON.stringify(string)，Vue 的 readJson 可直接解析回原值
  await page.goto('/chat/new')
  await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}/)
  const threadId = new URL(page.url()).pathname.split('/').pop() ?? ''

  const rawThreadId = await readStorageRaw(page, 'sessionStorage', AGENT_THREAD_KEY)
  expect(rawThreadId).toBe(JSON.stringify(threadId))
  const parsedThreadId = JSON.parse(rawThreadId ?? 'null') as unknown
  expect(typeof parsedThreadId).toBe('string')
  expect(parsedThreadId).toBe(threadId)
})
