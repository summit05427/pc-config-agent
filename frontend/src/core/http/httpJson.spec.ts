import {
  AxiosError,
  AxiosHeaders,
  CanceledError,
  type AxiosAdapter,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({ toast: { error: vi.fn() } }))

import { toast } from 'sonner'

import { ApiError, NETWORK_ERROR_MESSAGE, TIMEOUT_ERROR_MESSAGE } from './api-error'
import { acceptToken, configureAuth, getAccessToken, resetAuthForTests } from './auth'
import { http } from './httpJson'

const createResponse = <T>(config: InternalAxiosRequestConfig, data: T): AxiosResponse => ({
  data: { code: 0, data, message: 'ok', requestId: 'req-1' },
  status: 200,
  statusText: 'OK',
  headers: new AxiosHeaders({ 'x-request-id': 'req-1' }),
  config,
})

const createUnauthorizedError = (config: InternalAxiosRequestConfig): Promise<AxiosResponse> =>
  Promise.reject(
    new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, undefined, {
      data: { code: 20001, message: '登录状态已失效' },
      status: 401,
      statusText: 'Unauthorized',
      headers: new AxiosHeaders({ 'x-request-id': 'req-401' }),
      config,
    }),
  )

describe('http 成功与业务错误', () => {
  beforeEach(() => {
    resetAuthForTests()
  })

  it('业务码为 0 时直接返回信封中的 data', async () => {
    const adapter: AxiosAdapter = async (config) => createResponse(config, { id: 1 })

    await expect(http.get<{ id: number }>('/demo', { adapter })).resolves.toEqual({ id: 1 })
  })

  it('业务码非 0 抛 ApiError，保留错误码与 requestId', async () => {
    const adapter: AxiosAdapter = async (config) => ({
      ...createResponse(config, undefined),
      data: { code: 40001, message: '用户名或密码错误', requestId: 'req-biz' },
    })

    const error = await http
      .post('/auth/login', { username: 'a', password: 'b' }, { adapter, silent: true })
      .catch((reason: unknown) => reason)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ code: 40001, message: '用户名或密码错误', requestId: 'req-biz' })
  })

  it('缺失 requestId 时回退到 X-Request-Id 响应头', async () => {
    const adapter: AxiosAdapter = async (config) => ({
      ...createResponse(config, undefined),
      data: { code: 40001, message: '业务失败' },
    })

    const error = await http
      .get('/demo', { adapter, silent: true })
      .catch((reason: unknown) => reason)

    expect(error).toMatchObject({ requestId: 'req-1' })
  })

  it('非 silent 业务失败会弹全局提示，silent 时不弹', async () => {
    const adapter: AxiosAdapter = async (config) => ({
      ...createResponse(config, undefined),
      data: { code: 40001, message: '业务失败' },
    })

    await expect(http.get('/demo', { adapter })).rejects.toBeInstanceOf(ApiError)
    expect(toast.error).toHaveBeenCalledWith('业务失败')

    await expect(http.get('/demo', { adapter, silent: true })).rejects.toBeInstanceOf(ApiError)
    expect(toast.error).toHaveBeenCalledTimes(1)
  })
})

describe('http 网络与 HTTP 错误', () => {
  beforeEach(() => {
    resetAuthForTests()
  })

  it('网络失败归一化为 ApiError', async () => {
    const adapter: AxiosAdapter = (config) =>
      Promise.reject(new AxiosError('Network Error', 'ERR_NETWORK', config))

    await expect(http.get('/demo', { adapter, silent: true })).rejects.toMatchObject({
      message: NETWORK_ERROR_MESSAGE,
      code: 'ERR_NETWORK',
    })
  })

  it('超时使用统一的超时文案', async () => {
    const adapter: AxiosAdapter = (config) =>
      Promise.reject(new AxiosError('timeout exceeded', 'ECONNABORTED', config))

    await expect(http.get('/demo', { adapter, silent: true })).rejects.toMatchObject({
      message: TIMEOUT_ERROR_MESSAGE,
    })
  })

  it('主动取消的请求保持原始取消错误，不弹提示', async () => {
    const cancellation = new CanceledError('canceled')
    const adapter: AxiosAdapter = () => Promise.reject(cancellation)

    await expect(http.get('/demo', { adapter })).rejects.toBe(cancellation)
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('常规 HTTP 错误按状态码映射文案并带上 requestId', async () => {
    const adapter: AxiosAdapter = (config) =>
      Promise.reject(
        new AxiosError('Bad Request', 'ERR_BAD_REQUEST', config, undefined, {
          data: {},
          status: 400,
          statusText: 'Bad Request',
          headers: new AxiosHeaders({ 'x-request-id': 'req-400' }),
          config,
        }),
      )

    await expect(http.get('/demo', { adapter, silent: true })).rejects.toMatchObject({
      status: 400,
      message: '请求参数有误',
      requestId: 'req-400',
    })
  })
})

describe('http 401 刷新与重放', () => {
  beforeEach(() => {
    resetAuthForTests()
  })

  it('并发 401 只刷新一次，每个请求各重放一次', async () => {
    let refreshCount = 0
    configureAuth({
      refresh: async () => {
        refreshCount += 1
        acceptToken('fresh-token')
        return 'fresh-token'
      },
      onUnauthorized: () => undefined,
    })

    const attempts = new Map<string, number>()
    const adapter: AxiosAdapter = async (config) => {
      const url = config.url ?? ''
      const attempt = (attempts.get(url) ?? 0) + 1
      attempts.set(url, attempt)

      if (attempt === 1) {
        return createUnauthorizedError(config)
      }
      return createResponse(config, { url })
    }

    const results = await Promise.all([
      http.get<{ url: string }>('/protected-a', { adapter }),
      http.get<{ url: string }>('/protected-b', { adapter }),
      http.get<{ url: string }>('/protected-c', { adapter }),
    ])

    expect(refreshCount).toBe(1)
    expect(attempts.get('/protected-a')).toBe(2)
    expect(attempts.get('/protected-b')).toBe(2)
    expect(attempts.get('/protected-c')).toBe(2)
    expect(results).toEqual([
      { url: '/protected-a' },
      { url: '/protected-b' },
      { url: '/protected-c' },
    ])
  })

  it('重放后仍 401 则清理登录态并只通知一次，不再刷新', async () => {
    let refreshCount = 0
    const onUnauthorized = vi.fn()
    configureAuth({
      refresh: async () => {
        refreshCount += 1
        return 'fresh-token'
      },
      onUnauthorized,
    })

    const adapter: AxiosAdapter = (config) => createUnauthorizedError(config)

    await expect(http.get('/protected', { adapter, silent: true })).rejects.toMatchObject({
      status: 401,
    })
    expect(refreshCount).toBe(1)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
    expect(getAccessToken()).toBe('')
  })

  it('认证端点自身的 401 不触发刷新，也不触发全局跳转', async () => {
    let refreshCount = 0
    const onUnauthorized = vi.fn()
    configureAuth({
      refresh: async () => {
        refreshCount += 1
        return 'fresh-token'
      },
      onUnauthorized,
    })

    const adapter: AxiosAdapter = (config) => createUnauthorizedError(config)

    await expect(
      http.post('/auth/refresh', undefined, { adapter, silent: true, authPolicy: 'no-redirect' }),
    ).rejects.toMatchObject({ status: 401 })
    expect(refreshCount).toBe(0)
    expect(onUnauthorized).not.toHaveBeenCalled()
  })
})

describe('http 幂等键', () => {
  beforeEach(() => {
    resetAuthForTests()
  })

  it('写请求携带 Idempotency-Key，并在 401 重放时沿用同一个值', async () => {
    const receivedKeys: Array<string | null> = []
    let attempt = 0

    configureAuth({
      refresh: async () => {
        acceptToken('fresh-token')
        return 'fresh-token'
      },
      onUnauthorized: () => undefined,
    })

    const adapter: AxiosAdapter = async (config) => {
      const idempotencyKey = config.headers.get('Idempotency-Key')
      receivedKeys.push(typeof idempotencyKey === 'string' ? idempotencyKey : null)
      attempt += 1
      if (attempt === 1) {
        return createUnauthorizedError(config)
      }
      return createResponse(config, { created: true })
    }

    await http.post('/orders', { amount: 100 }, { adapter, idempotencyKey: 'order-1' })

    expect(receivedKeys).toEqual(['order-1', 'order-1'])
    expect(attempt).toBe(2)
  })

  it('普通读请求不发送 Idempotency-Key', async () => {
    const adapter: AxiosAdapter = async (config) => {
      expect(config.headers.get('Idempotency-Key')).toBeUndefined()
      return createResponse(config, { items: [] })
    }

    await http.get('/orders', { adapter })
  })
})
