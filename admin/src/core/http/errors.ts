import { AxiosError } from 'axios'
import type { ApiEnvelope } from './types'

/**
 * 归一化后的接口错误。
 *
 * `code` 是业务码（0 表示成功），`status` 是 HTTP 状态码，两者都保留，
 * 便于区分「业务拒绝」与「协议层失败」。
 */
export class ApiError extends Error {
  readonly code: number
  readonly status: number
  readonly requestId?: string

  constructor(
    message: string,
    options: { code: number; status: number; requestId?: string }
  ) {
    super(message)
    this.name = 'ApiError'
    this.code = options.code
    this.status = options.status
    this.requestId = options.requestId
  }
}

/** 把任意异常收敛成 ApiError，避免调用方各自判断异常类型。 */
export function normalizeError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error
  }

  if (error instanceof AxiosError) {
    const envelope = error.response?.data as
      | Partial<ApiEnvelope<unknown>>
      | undefined
    const status = error.response?.status ?? 0
    const message =
      (typeof envelope?.message === 'string' && envelope.message) ||
      getStatusMessage(status)
    return new ApiError(message, {
      code: typeof envelope?.code === 'number' ? envelope.code : status,
      status,
      requestId: envelope?.requestId,
    })
  }

  if (error instanceof Error && error.message) {
    return new ApiError(error.message, { code: 0, status: 0 })
  }

  return new ApiError('请求失败，请稍后重试', { code: 0, status: 0 })
}

/** 面向用户的错误提示，UI 层只调用它，不直接读 axios 结构。 */
export function getHttpErrorMessage(error: unknown): string {
  return normalizeError(error).message
}

function getStatusMessage(status: number): string {
  if (status === 0) return '网络连接失败，请检查网络后重试'
  if (status === 401) return '登录状态已失效，请重新登录'
  if (status === 403) return '没有权限执行该操作'
  if (status === 404) return '请求的资源不存在'
  if (status === 409) return '操作与当前数据状态冲突，请刷新后重试'
  if (status === 429) return '操作过于频繁，请稍后再试'
  if (status >= 500) return '服务暂时不可用，请稍后重试'
  return '请求失败，请稍后重试'
}
