import { describe, expect, it } from 'vitest'

import { HTTP_STATUS } from '@/constants/http'

import {
  ApiError,
  DEFAULT_ERROR_MESSAGE,
  getHttpErrorMessage,
  isRetriableError,
  normalizeError,
} from './api-error'

describe('getHttpErrorMessage', () => {
  it('已登记的状态码返回对应文案', () => {
    expect(getHttpErrorMessage(HTTP_STATUS.BAD_REQUEST)).toBe('请求参数有误')
    expect(getHttpErrorMessage(HTTP_STATUS.UNAUTHORIZED)).toBe('登录状态已失效，请重新登录')
    expect(getHttpErrorMessage(HTTP_STATUS.NOT_FOUND)).toBe('请求的资源不存在')
  })

  it('未登记或缺失状态码回退到默认文案', () => {
    expect(getHttpErrorMessage(418)).toBe(DEFAULT_ERROR_MESSAGE)
    expect(getHttpErrorMessage()).toBe(DEFAULT_ERROR_MESSAGE)
  })
})

describe('normalizeError', () => {
  it('ApiError 原样返回，保留业务码与 requestId', () => {
    const error = new ApiError('业务失败', { code: 40001, status: 400, requestId: 'req-1' })

    expect(normalizeError(error)).toBe(error)
  })

  it('原生 Error 包装为 ApiError 并保留 cause', () => {
    const cause = new Error('boom')
    const normalized = normalizeError(cause)

    expect(normalized).toBeInstanceOf(ApiError)
    expect(normalized.message).toBe('boom')
    expect(normalized.code).toBe('UNKNOWN')
    expect(normalized.cause).toBe(cause)
  })

  it('非 Error 值回退到默认文案，不泄露原始内容', () => {
    const normalized = normalizeError({ secret: 'x' })

    expect(normalized.message).toBe(DEFAULT_ERROR_MESSAGE)
    expect(normalized.code).toBe('UNKNOWN')
  })
})

describe('isRetriableError', () => {
  it('网络异常没有状态码时允许重试', () => {
    expect(isRetriableError(new ApiError('网络异常'))).toBe(true)
  })

  it('4xx 默认不重试，401 与 403 都不重试', () => {
    expect(isRetriableError(new ApiError('无权限', { status: 401 }))).toBe(false)
    expect(isRetriableError(new ApiError('无权限', { status: 403 }))).toBe(false)
    expect(isRetriableError(new ApiError('不存在', { status: 404 }))).toBe(false)
  })

  it('408 与 429 属于可重试的 4xx', () => {
    expect(isRetriableError(new ApiError('超时', { status: 408 }))).toBe(true)
    expect(isRetriableError(new ApiError('限流', { status: 429 }))).toBe(true)
  })

  it('5xx 允许重试', () => {
    expect(isRetriableError(new ApiError('服务异常', { status: 500 }))).toBe(true)
  })
})
