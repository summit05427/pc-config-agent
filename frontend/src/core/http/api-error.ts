import { HTTP_STATUS } from '@/constants/http'

/** Java 统一响应信封中表示成功的业务码 */
export const SUCCESS_CODE = 0

export const DEFAULT_ERROR_MESSAGE = '请求失败，请稍后重试'
export const NETWORK_ERROR_MESSAGE = '网络异常，请检查网络连接'
export const TIMEOUT_ERROR_MESSAGE = '请求超时，请稍后重试'

/**
 * HTTP 状态码到可读文案的唯一映射。
 *
 * 请求层、Agent 请求与流式入口都从这里取文案，禁止在各处 catch 里手写。
 */
const HTTP_ERROR_MESSAGES: Record<number, string> = {
  [HTTP_STATUS.BAD_REQUEST]: '请求参数有误',
  [HTTP_STATUS.UNAUTHORIZED]: '登录状态已失效，请重新登录',
  [HTTP_STATUS.FORBIDDEN]: '没有访问权限',
  [HTTP_STATUS.NOT_FOUND]: '请求的资源不存在',
  [HTTP_STATUS.INTERNAL_SERVER_ERROR]: '服务器内部错误',
}

export const getHttpErrorMessage = (status?: number): string =>
  (status !== undefined ? HTTP_ERROR_MESSAGES[status] : undefined) ?? DEFAULT_ERROR_MESSAGE

export interface ApiErrorOptions {
  /** Java 业务码，或 Axios / fetch 的错误码（如 ERR_NETWORK） */
  code?: number | string
  status?: number
  /** 与响应头 X-Request-Id 一致的排查标识 */
  requestId?: string
  cause?: unknown
}

/** 请求层统一抛出的错误类型，调用方据此区分业务错误、网络异常与 HTTP 状态错误 */
export class ApiError extends Error {
  readonly code: number | string
  readonly status?: number
  readonly requestId?: string

  constructor(message: string, options: ApiErrorOptions = {}) {
    super(message, { cause: options.cause })
    this.name = 'ApiError'
    this.code = options.code ?? 'UNKNOWN'
    this.status = options.status
    this.requestId = options.requestId
  }
}

/** 把任意 catch 到的值归一化为 ApiError，保证 Query 与组件只处理一种错误类型 */
export const normalizeError = (error: unknown): ApiError => {
  if (error instanceof ApiError) {
    return error
  }

  if (error instanceof Error) {
    return new ApiError(error.message, { code: 'UNKNOWN', cause: error })
  }

  return new ApiError(DEFAULT_ERROR_MESSAGE, { code: 'UNKNOWN', cause: error })
}

const RETRIABLE_STATUS_CODES = new Set([408, 429])

/**
 * Query 重试判定：4xx 不重试（401 由刷新逻辑处理），408/429 与服务端 5xx 才重试。
 */
export const isRetriableError = (error: unknown): boolean => {
  const normalized = normalizeError(error)
  if (normalized.status === undefined) {
    return true
  }

  if (normalized.status >= 400 && normalized.status < 500) {
    return RETRIABLE_STATUS_CODES.has(normalized.status)
  }

  return true
}
