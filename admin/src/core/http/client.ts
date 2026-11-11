import axios, {
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'
import { env } from '@/lib/env'
import { useAuthStore } from '@/stores/auth-store'
import { ApiError, normalizeError } from './errors'
import type { ApiEnvelope } from './types'

const REFRESH_PATH = '/auth/refresh'
/** 这些接口自身返回 401 时不能触发刷新，否则会形成刷新死循环。 */
const NON_RETRIABLE_PATHS = ['/auth/login', '/auth/logout', REFRESH_PATH]

interface RetriableConfig extends InternalAxiosRequestConfig {
  _isRetried?: boolean
}

export const httpClient = axios.create({
  baseURL: env.apiBaseUrl,
  timeout: 15_000,
  // 刷新令牌只存在于 HttpOnly Cookie，必须允许携带凭证
  withCredentials: true,
})

let refreshPromise: Promise<string | null> | null = null
let unauthorizedHandler: (() => void) | null = null

/** 会话彻底失效时的兜底动作（跳转登录页），由应用入口注册。 */
export function setUnauthorizedHandler(handler: () => void): void {
  unauthorizedHandler = handler
}

/**
 * 刷新访问令牌，多个并发 401 只发起一次请求（单飞）。
 *
 * 返回 null 表示刷新失败，调用方负责清理本地会话。
 */
export async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = requestRefreshToken().finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

async function requestRefreshToken(): Promise<string | null> {
  try {
    // 用裸 axios 而非 httpClient：避免刷新请求再次进入拦截器
    const response = await axios.post<ApiEnvelope<{ accessToken: string }>>(
      `${env.apiBaseUrl}${REFRESH_PATH}`,
      null,
      { withCredentials: true, timeout: 10_000 }
    )
    const token = response.data.data?.accessToken
    if (!token) return null

    useAuthStore.getState().auth.setAccessToken(token)
    return token
  } catch {
    // 刷新失败的具体原因交由调用方统一处理，这里不弹提示
    return null
  }
}

httpClient.interceptors.request.use((config) => {
  const { accessToken } = useAuthStore.getState().auth
  if (accessToken && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${accessToken}`
  }
  return config
})

httpClient.interceptors.response.use(
  (response) => {
    const envelope = response.data as ApiEnvelope<unknown> | undefined
    // 非信封响应（如 204）原样返回，交由调用方处理
    if (!envelope || typeof envelope.code !== 'number') {
      return response
    }
    if (envelope.code !== 0) {
      throw new ApiError(envelope.message ?? '请求失败，请稍后重试', {
        code: envelope.code,
        status: response.status,
        requestId: envelope.requestId,
      })
    }
    response.data = envelope.data
    return response
  },
  async (error: unknown) => {
    const normalized = normalizeError(error)
    if (normalized.status !== 401) {
      return Promise.reject(normalized)
    }

    const config = (error as { config?: RetriableConfig }).config
    const isNonRetriable = NON_RETRIABLE_PATHS.some((path) =>
      config?.url?.includes(path)
    )
    if (!config || config._isRetried || isNonRetriable) {
      return Promise.reject(normalized)
    }

    const token = await refreshAccessToken()
    if (!token) {
      useAuthStore.getState().auth.reset()
      unauthorizedHandler?.()
      return Promise.reject(normalized)
    }

    config._isRetried = true
    config.headers.Authorization = `Bearer ${token}`
    return httpClient.request(config)
  }
)

/**
 * 发起请求并返回信封中的 `data`。
 *
 * 响应结构由调用方用 zod 校验，这里只负责解包与错误归一。
 */
export async function httpJson<T>(config: AxiosRequestConfig): Promise<T> {
  const response = await httpClient.request<T>(config)
  return response.data
}

/**
 * 下载类请求：直接返回原始响应体。
 *
 * 仅用于 CSV 等附件（响应不是 `{ code, data }` 信封），因此跳过信封解包；
 * 鉴权、401 刷新与错误归一仍复用同一组拦截器。
 */
export async function httpBlob(config: AxiosRequestConfig): Promise<Blob> {
  const response = await httpClient.request<Blob>({
    ...config,
    responseType: 'blob',
  })
  return response.data
}
