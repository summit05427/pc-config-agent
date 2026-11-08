import type { Page, Route } from '@playwright/test'

import type { SseScenario } from './sse-server'

/**
 * 对话 E2E 的 JSON 后端替身。
 *
 * 静态接口用 page.route 直接返回；SSE 需要逐帧时序与客户端中止，统一交给同目录的
 * sse-server，这里只负责把 /chat/stream 改写到该本地服务，并保留原有导出入口。
 */

export { startSseServer } from './sse-server'
export type { SseServerHandle } from './sse-server'

// 模型目录走 /api/v2，其余业务接口走 /api/v1；两版都要拦，避免测试流量落到真实后端
const API_PATTERN = '**/api/v*/**'
const APP_ORIGIN = 'http://localhost:5273'
/** Agent 走 /agent 代理前缀，本地绝对地址则没有前缀；统一去掉前缀后再比对路径 */
const AGENT_PREFIX = /^\/agent(?=\/api\/)/
const MESSAGES_PATTERN = /^\/api\/v1\/sessions\/([^/]+)\/messages$/
/** done 之后确认落库固定用 size=1，可据此区分「首屏查询」与「交接确认」 */
const CONFIRM_PAGE_SIZE = 1

export interface HistoryMessage {
  readonly role: string
  readonly content: string
  readonly name?: string
  readonly tool_calls?: ReadonlyArray<{ readonly name: string; readonly args: Record<string, unknown> }>
}

/** 会话列表条目，只含页面展示与断言需要的字段 */
export interface SessionSummary {
  readonly thread_id: string
  readonly title: string
  readonly model_key?: string | null
  readonly last_active_at?: string
}

export interface ChatBackendOptions {
  /** 由 startSseServer 提供，route.continue 会把 /chat/stream 改写到这里 */
  readonly sseUrl: string
  readonly scenario: SseScenario
  /** done 后历史重新同步返回的消息，按服务端 desc 顺序给出 */
  readonly history?: readonly HistoryMessage[]
  /** 深层链接场景：会话已落库，首屏查询就应成功 */
  readonly isPersistedInitially?: boolean
  /** 侧栏会话列表；缺省为空列表，保持既有用例的行为 */
  readonly sessions?: readonly SessionSummary[]
  /**
   * 按会话提供各自历史；一旦提供，命中的会话始终视为已落库，
   * 未命中的会话返回 404；新建会话不会查询历史，此分支覆盖直接访问不存在会话的场景。
   */
  readonly histories?: Readonly<Record<string, readonly HistoryMessage[]>>
}

export interface ChatBackendState {
  /** 历史接口累计请求次数，用于断言 done 之后确实发生了重新同步 */
  messageRequests: number
  isPersisted: boolean
}

const corsHeaders = (route: Route): Record<string, string> => {
  const origin = route.request().headers().origin ?? APP_ORIGIN

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
const SESSIONS_PAGE_SIZE = 20

/**
 * 注册对话页所需的全部 JSON mock 并返回可观测状态。
 *
 * SSE 请求仍由 page.route 拦截，再改写到本地流服务；其他请求直接返回信封或裸 JSON。
 */
export const mockChatBackend = async (
  page: Page,
  options: ChatBackendOptions,
): Promise<ChatBackendState> => {
  const state: ChatBackendState = {
    messageRequests: 0,
    isPersisted: options.isPersistedInitially ?? false,
  }
  const history = [...(options.history ?? [])]
  const sessions = [...(options.sessions ?? [])]

  await page.route(API_PATTERN, async (route) => {
    if (route.request().method() === 'OPTIONS') {
      return fulfillPreflight(route)
    }

    const path = new URL(route.request().url()).pathname.replace(AGENT_PREFIX, '')

    if (path.endsWith('/chat/stream')) {
      return route.continue({ url: `${options.sseUrl}?scenario=${options.scenario}` })
    }
    if (path.endsWith('/auth/refresh')) {
      return fulfillJson(route, envelope(refreshPayload))
    }
    if (path.endsWith('/auth/me')) {
      return fulfillJson(route, envelope(currentUser))
    }
    if (path === '/api/v2/models') {
      return fulfillJson(route, envelope({ list: [], total: 0, page: 1, size: 100 }))
    }
    if (path === '/api/v1/sessions') {
      return fulfillJson(route, {
        list: sessions,
        total: sessions.length,
        page: 1,
        size: SESSIONS_PAGE_SIZE,
      })
    }

    const messagesMatch = MESSAGES_PATTERN.exec(path)
    if (messagesMatch) {
      state.messageRequests += 1
      const url = new URL(route.request().url())
      const size = Number(url.searchParams.get('size') ?? '100')
      const threadId = decodeURIComponent(messagesMatch[1] ?? '')

      // 按会话提供历史时，每个会话独立且命中即视为已落库，便于模拟多会话切换
      if (options.histories) {
        const fixture = options.histories[threadId]
        if (!fixture) {
          return fulfillJson(route, { code: 40402, message: '会话尚未落库' }, 404)
        }
        return fulfillJson(route, {
          thread_id: threadId,
          list: fixture.slice(0, size),
          total: fixture.length,
          page: Number(url.searchParams.get('page') ?? '1'),
          size,
        })
      }

      // done 之后的确认请求只取 1 条，此时才认定会话已落库
      if (size === CONFIRM_PAGE_SIZE) {
        state.isPersisted = true
      }
      if (!state.isPersisted) {
        return fulfillJson(route, { code: 40402, message: '会话尚未落库' }, 404)
      }
      return fulfillJson(route, {
        thread_id: threadId,
        list: history.slice(0, size),
        total: history.length,
        page: Number(url.searchParams.get('page') ?? '1'),
        size,
      })
    }

    return fulfillJson(route, { code: 40401, message: '未 mock 的接口' }, 404)
  })

  return state
}
