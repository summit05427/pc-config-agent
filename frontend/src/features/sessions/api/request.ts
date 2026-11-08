import { toast } from 'sonner'

import {
  ApiError,
  NETWORK_ERROR_MESSAGE,
  authHeader,
  getHttpErrorMessage,
  handleUnauthorized,
} from '@/core/http'
import { HTTP_STATUS } from '@/constants/http'
import { env } from '@/shared/lib/env'

// Agent 服务返回裸 JSON 与 SSE，不使用 Java 的 { code, message, data } 信封，
// 因此这里不复用 httpJson，而是用 fetch 单独实现。
const NETWORK_ERROR_CODE = 'NETWORK_ERROR'
const INVALID_RESPONSE_MESSAGE = '响应解析失败'
const JSON_ACCEPT = 'application/json'

export type AgentHttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export interface AgentRequestInit {
  method?: AgentHttpMethod
  body?: string
  signal?: AbortSignal
  headers?: Record<string, string>
  /** 关闭自动 toast，由调用方自行处理并回滚（如会话模型切换） */
  silent?: boolean
}

type AgentQuery = Record<string, string | number | undefined>

interface ErrorPayload {
  code?: unknown
  message?: unknown
  detail?: unknown
}

const isAbortError = (error: unknown): boolean =>
  error instanceof Error && error.name === 'AbortError'

/**
 * 拼接 Agent 服务地址。
 *
 * 允许同源相对前缀（/agent/api/v1）与绝对地址；以 window.location.origin 作为
 * 相对地址的基址，保证 URL 构造在浏览器与测试环境一致。
 */
export const buildAgentUrl = (path: string, query?: AgentQuery): string => {
  const base = env.agentBaseUrl.endsWith('/') ? env.agentBaseUrl.slice(0, -1) : env.agentBaseUrl
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const url = new URL(`${base}${normalizedPath}`, window.location.origin)

  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined) {
      url.searchParams.set(key, String(value))
    }
  }

  return url.toString()
}

/**
 * 带 Access Token 的 fetch，401 交给 auth 模块决策后最多重放一次。
 *
 * 只处理响应头已到达、流尚未消费的 401；流开始读取后不再重发，
 * 避免重复执行带副作用的工具调用。
 */
const fetchWithAuth = async (url: string, init: AgentRequestInit): Promise<Response> => {
  const send = (): Promise<Response> =>
    fetch(url, { ...init, headers: { ...authHeader(), ...init.headers } })

  const response = await send()
  if (response.status !== HTTP_STATUS.UNAUTHORIZED) {
    return response
  }

  const action = await handleUnauthorized()
  if (action !== 'replay') {
    return response
  }

  // 重放时重新取 Token：刷新后内存里已经是新值，不能用第一次的请求头复用
  const replayed = await send()
  if (replayed.status !== HTTP_STATUS.UNAUTHORIZED) {
    return replayed
  }

  // 重放后仍 401：交给 auth 模块清理并触发全局跳转，错误由调用方归一化
  await handleUnauthorized({ isReplayed: true })
  return replayed
}

const readErrorPayload = async (
  response: Response,
): Promise<{ code: string | number; message: string }> => {
  let payload: ErrorPayload = {}

  try {
    const parsed: unknown = await response.json()
    if (typeof parsed === 'object' && parsed !== null) {
      payload = parsed as ErrorPayload
    }
  } catch {
    // 网关或代理可能返回 HTML，解析失败时按状态码兜底
  }

  const code =
    typeof payload.code === 'string' || typeof payload.code === 'number'
      ? payload.code
      : response.status
  const message =
    typeof payload.message === 'string'
      ? payload.message
      : typeof payload.detail === 'string'
        ? payload.detail
        : getHttpErrorMessage(response.status)

  return { code, message }
}

const handleHttpError = async (response: Response, silent = false): Promise<ApiError> => {
  const { code, message } = await readErrorPayload(response)

  if (response.status === HTTP_STATUS.UNAUTHORIZED) {
    // 401 的刷新、清理与跳转已在 fetchWithAuth 完成，这里只构造错误
    return new ApiError(message, { code, status: response.status })
  }

  // 404 交给调用方判断（历史查询中表示会话不存在），不在这里弹提示
  if (!silent && response.status !== HTTP_STATUS.NOT_FOUND) {
    toast.error(message)
  }

  return new ApiError(message, { code, status: response.status })
}

/**
 * 发送 Agent 请求并返回已确认成功的响应。
 *
 * 网络异常、401 刷新失败与业务 HTTP 错误都会抛出 ApiError；
 * 主动取消的请求保持原始 AbortError，便于调用方区分「用户停止」与「真实失败」。
 */
export const sendAgentRequest = async (
  path: string,
  init: AgentRequestInit,
  query?: AgentQuery,
): Promise<Response> => {
  let response: Response

  try {
    response = await fetchWithAuth(buildAgentUrl(path, query), {
      ...init,
      headers: { Accept: JSON_ACCEPT, ...init.headers },
    })
  } catch (error) {
    if (isAbortError(error)) {
      throw error
    }
    if (!init.silent) {
      toast.error(NETWORK_ERROR_MESSAGE)
    }
    throw new ApiError(NETWORK_ERROR_MESSAGE, { code: NETWORK_ERROR_CODE })
  }

  if (!response.ok) {
    throw await handleHttpError(response, init.silent)
  }

  return response
}

export const requestAgentJson = async <T>(
  path: string,
  init: AgentRequestInit,
  query?: AgentQuery,
): Promise<T> => {
  const response = await sendAgentRequest(path, init, query)

  try {
    return (await response.json()) as T
  } catch {
    throw new ApiError(INVALID_RESPONSE_MESSAGE, { status: response.status })
  }
}

/** 删除接口返回 204 且无响应体，不能复用 JSON 解析 */
export const requestAgentVoid = async (path: string, init: AgentRequestInit): Promise<void> => {
  await sendAgentRequest(path, init)
}

export { INVALID_RESPONSE_MESSAGE, NETWORK_ERROR_CODE }
