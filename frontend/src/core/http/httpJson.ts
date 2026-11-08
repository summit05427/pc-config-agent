import axios, {
  AxiosHeaders,
  type AxiosError,
  type AxiosRequestConfig,
  type AxiosResponse,
} from 'axios'
import { toast } from 'sonner'

import { HTTP_STATUS } from '@/constants/http'
import { env } from '@/shared/lib/env'

import {
  ApiError,
  DEFAULT_ERROR_MESSAGE,
  NETWORK_ERROR_MESSAGE,
  SUCCESS_CODE,
  TIMEOUT_ERROR_MESSAGE,
  getHttpErrorMessage,
} from './api-error'
import { AUTHORIZATION_HEADER, authHeader, handleUnauthorized, type AuthPolicy } from './auth'

const TIMEOUT_ERROR_CODE = 'ECONNABORTED'
const REQUEST_ID_HEADER = 'x-request-id'
const IDEMPOTENCY_HEADER = 'Idempotency-Key'

/** Java 统一响应信封 */
export interface ApiResponse<T> {
  code: number
  data?: T
  message: string
  /** 与响应头 X-Request-Id 一致，便于排查 */
  requestId?: string
}

interface RetriableRequestConfig extends HttpClientConfig {
  // 标记该请求已因 401 重试过，避免刷新成功但接口仍 401 时无限循环
  isAuthRetried?: boolean
}

interface InternalHttpRequestConfig extends AxiosRequestConfig {
  idempotencyKey?: string
}

/**
 * 统一请求配置。
 *
 * `silent` 用于能力探测类请求（如模型目录），失败时由调用方静默降级，
 * 不弹全局 toast 打断当前页面操作。
 */
export interface HttpClientConfig extends AxiosRequestConfig {
  silent?: boolean
  /** 写请求的幂等键，401 重放时沿用同一个值，服务端可据此去重 */
  idempotencyKey?: string
  /** 401 之后的行为策略；缺省为 `default`，认证端点由调用方显式声明 */
  authPolicy?: AuthPolicy
}

const readHeader = (headers: unknown, name: string): string | undefined => {
  if (headers instanceof AxiosHeaders) {
    const value = headers.get(name)
    return typeof value === 'string' ? value : undefined
  }

  if (typeof headers !== 'object' || headers === null) {
    return undefined
  }

  const value = (headers as Record<string, unknown>)[name]
  return typeof value === 'string' ? value : undefined
}

const httpClient = axios.create({
  baseURL: env.apiBaseUrl,
  timeout: env.apiTimeout,
})

httpClient.interceptors.request.use((config) => {
  const authorization = authHeader()[AUTHORIZATION_HEADER]
  if (authorization) {
    config.headers.set(AUTHORIZATION_HEADER, authorization)
  }

  const idempotencyKey = (config as InternalHttpRequestConfig).idempotencyKey
  if (idempotencyKey) {
    config.headers.set(IDEMPOTENCY_HEADER, idempotencyKey)
  }

  return config
})

httpClient.interceptors.response.use(
  (response: AxiosResponse<unknown>) => {
    const payload = response.data as ApiResponse<unknown> | undefined
    const config = response.config as HttpClientConfig | undefined

    // 非约定结构的响应（如文件流）不做业务码校验，由调用方单独处理
    if (!payload || typeof payload.code !== 'number') {
      return response
    }

    if (payload.code !== SUCCESS_CODE) {
      const message = payload.message || DEFAULT_ERROR_MESSAGE
      if (!config?.silent) {
        toast.error(message)
      }
      return Promise.reject(
        new ApiError(message, {
          code: payload.code,
          status: response.status,
          requestId: payload.requestId ?? readHeader(response.headers, REQUEST_ID_HEADER),
        }),
      )
    }

    return response
  },
  async (error: AxiosError<ApiResponse<unknown>>) => {
    // 主动取消的请求不上报错误，避免切换页面时弹出无意义提示
    if (axios.isCancel(error)) {
      return Promise.reject(error)
    }

    const status = error.response?.status

    if (status === HTTP_STATUS.UNAUTHORIZED) {
      const config = error.config as RetriableRequestConfig | undefined

      // 401 的刷新、清理与跳转全部由 auth 模块决定；适配器只负责按结果重放
      const action = await handleUnauthorized({
        policy: config?.authPolicy,
        isReplayed: config?.isAuthRetried,
      })

      if (action === 'replay' && config) {
        config.isAuthRetried = true
        return httpClient.request(config)
      }

      // 401 不额外弹提示避免重复打扰；认证端点由调用方内联处理
      return Promise.reject(
        new ApiError(getHttpErrorMessage(status), {
          status,
          requestId: readHeader(error.response?.headers, REQUEST_ID_HEADER),
        }),
      )
    }

    const message =
      error.code === TIMEOUT_ERROR_CODE
        ? TIMEOUT_ERROR_MESSAGE
        : status
          ? getHttpErrorMessage(status)
          : NETWORK_ERROR_MESSAGE

    // 错误分支的 config 不在 401 块作用域内，需要单独读取才能尊重调用方的 silent 意图
    const requestConfig = error.config as HttpClientConfig | undefined
    if (!requestConfig?.silent) {
      toast.error(message)
    }

    return Promise.reject(
      new ApiError(message, {
        status,
        code: error.code,
        requestId: readHeader(error.response?.headers, REQUEST_ID_HEADER),
        cause: error,
      }),
    )
  },
)

/** 统一请求入口：返回值直接是契约中的 data，失败时抛出 ApiError */
export const request = async <T>(config: HttpClientConfig): Promise<T> => {
  const response = await httpClient.request<ApiResponse<T>>(config)
  // 后端成功响应必定带 data；无返回值的接口（如删除）在调用处声明为 void
  return response.data.data as T
}

// 简写方法固定 url / method，避免调用处覆盖，其余配置保持可扩展
export const http = {
  get: <T>(url: string, config?: HttpClientConfig): Promise<T> =>
    request<T>({ ...config, url, method: 'GET' }),
  post: <T>(url: string, data?: unknown, config?: HttpClientConfig): Promise<T> =>
    request<T>({ ...config, url, method: 'POST', data }),
  put: <T>(url: string, data?: unknown, config?: HttpClientConfig): Promise<T> =>
    request<T>({ ...config, url, method: 'PUT', data }),
  patch: <T>(url: string, data?: unknown, config?: HttpClientConfig): Promise<T> =>
    request<T>({ ...config, url, method: 'PATCH', data }),
  delete: <T>(url: string, config?: HttpClientConfig): Promise<T> =>
    request<T>({ ...config, url, method: 'DELETE' }),
}
