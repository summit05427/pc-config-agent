import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  acceptToken,
  authHeader,
  clearToken,
  configureAuth,
  getAccessToken,
  handleUnauthorized,
  refreshOnce,
  resetAuthForTests,
} from './auth'

describe('auth 模块', () => {
  const refresh = vi.fn<() => Promise<string | null>>()
  const onUnauthorized = vi.fn()

  beforeEach(() => {
    resetAuthForTests()
    refresh.mockReset()
    refresh.mockResolvedValue(null)
    onUnauthorized.mockReset()
    configureAuth({ refresh, onUnauthorized })
  })

  describe('令牌', () => {
    it('只保存内存副本，并生成 Bearer 头', () => {
      expect(authHeader()).toEqual({})

      acceptToken('token-1')
      expect(getAccessToken()).toBe('token-1')
      expect(authHeader()).toEqual({ Authorization: 'Bearer token-1' })
    })

    it('清理令牌后同时丢弃进行中的刷新', async () => {
      refresh.mockImplementationOnce(() => new Promise<string | null>(() => undefined))
      refresh.mockResolvedValueOnce('second-token')

      void refreshOnce()
      clearToken()

      expect(getAccessToken()).toBe('')
      // 引用已被丢弃，下一次调用会重新发起刷新
      await expect(refreshOnce()).resolves.toBe('second-token')
      expect(refresh).toHaveBeenCalledTimes(2)
    })

    it('acceptToken 重置全局跳转的单飞标记', async () => {
      await handleUnauthorized()
      expect(onUnauthorized).toHaveBeenCalledTimes(1)

      acceptToken('token-2')
      await handleUnauthorized()
      expect(onUnauthorized).toHaveBeenCalledTimes(2)
    })
  })

  describe('刷新单飞', () => {
    it('并发调用共享同一次刷新', async () => {
      refresh.mockImplementation(async () => {
        acceptToken('fresh-token')
        return 'fresh-token'
      })

      const tokens = await Promise.all([refreshOnce(), refreshOnce(), refreshOnce()])

      expect(refresh).toHaveBeenCalledTimes(1)
      expect(tokens).toEqual(['fresh-token', 'fresh-token', 'fresh-token'])
    })

    it('刷新异常返回 null，不向上抛异常', async () => {
      refresh.mockRejectedValue(new Error('cookie expired'))

      await expect(refreshOnce()).resolves.toBeNull()
    })

    it('未装配刷新实现时直接返回 null', async () => {
      resetAuthForTests()

      await expect(refreshOnce()).resolves.toBeNull()
    })
  })

  describe('401 决策', () => {
    it('default：刷新成功后返回 replay，不清令牌', async () => {
      refresh.mockImplementation(async () => {
        acceptToken('fresh-token')
        return 'fresh-token'
      })

      await expect(handleUnauthorized()).resolves.toBe('replay')
      expect(getAccessToken()).toBe('fresh-token')
      expect(onUnauthorized).not.toHaveBeenCalled()
    })

    it('default：刷新失败后清理令牌并跳转', async () => {
      acceptToken('expired-token')

      await expect(handleUnauthorized()).resolves.toBe('redirect')
      expect(getAccessToken()).toBe('')
      expect(onUnauthorized).toHaveBeenCalledTimes(1)
    })

    it('已重放过一次后不再刷新，直接清理并跳转', async () => {
      acceptToken('expired-token')

      await expect(handleUnauthorized({ isReplayed: true })).resolves.toBe('redirect')
      expect(refresh).not.toHaveBeenCalled()
      expect(getAccessToken()).toBe('')
    })

    it('no-refresh：跳过刷新，但仍清理并跳转', async () => {
      acceptToken('expired-token')

      await expect(handleUnauthorized({ policy: 'no-refresh' })).resolves.toBe('redirect')
      expect(refresh).not.toHaveBeenCalled()
      expect(getAccessToken()).toBe('')
      expect(onUnauthorized).toHaveBeenCalledTimes(1)
    })

    it('no-redirect：原样交给调用方，不刷新不清理不跳转', async () => {
      acceptToken('still-valid')

      await expect(handleUnauthorized({ policy: 'no-redirect' })).resolves.toBe('reject')
      expect(refresh).not.toHaveBeenCalled()
      expect(getAccessToken()).toBe('still-valid')
      expect(onUnauthorized).not.toHaveBeenCalled()
    })

    it('isolated：刷新成功后返回 replay', async () => {
      refresh.mockImplementation(async () => {
        acceptToken('fresh-token')
        return 'fresh-token'
      })

      await expect(handleUnauthorized({ policy: 'isolated' })).resolves.toBe('replay')
      expect(getAccessToken()).toBe('fresh-token')
      expect(onUnauthorized).not.toHaveBeenCalled()
    })

    it('isolated：刷新成功但重放仍 401 时保留登录态', async () => {
      acceptToken('still-valid')

      await expect(
        handleUnauthorized({ policy: 'isolated', isReplayed: true }),
      ).resolves.toBe('reject')
      expect(refresh).not.toHaveBeenCalled()
      expect(getAccessToken()).toBe('still-valid')
      expect(onUnauthorized).not.toHaveBeenCalled()
    })

    it('isolated：刷新失败说明会话过期，仍清理并跳转', async () => {
      acceptToken('expired-token')

      await expect(handleUnauthorized({ policy: 'isolated' })).resolves.toBe('redirect')
      expect(getAccessToken()).toBe('')
      expect(onUnauthorized).toHaveBeenCalledTimes(1)
    })

    it('并发 401 只触发一次全局跳转', async () => {
      await Promise.all([handleUnauthorized(), handleUnauthorized(), handleUnauthorized()])

      expect(onUnauthorized).toHaveBeenCalledTimes(1)
    })
  })
})
