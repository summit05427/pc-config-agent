import type { QueryClient } from '@tanstack/react-query'
import { isRedirect, type ParsedLocation } from '@tanstack/react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/features/auth/model/auth-session', () => ({
  ensureAuthSession: vi.fn(),
}))

import { currentUserQueryOptions } from '@/features/auth/api'
import { ensureAuthSession } from '@/features/auth/model/auth-session'
import { queryKeys } from '@/shared/lib/query-keys'

import { redirectAuthenticatedUser, requireAuthenticated } from './guards'

const createLocation = (href: string): ParsedLocation => ({ href }) as ParsedLocation

const captureRedirect = async (action: () => Promise<void>): Promise<unknown> => {
  try {
    await action()
  } catch (error) {
    return error
  }
  return undefined
}

describe('requireAuthenticated', () => {
  beforeEach(() => {
    vi.mocked(ensureAuthSession).mockReset()
  })

  it('未登录时重定向到登录页并携带完整回跳地址', async () => {
    vi.mocked(ensureAuthSession).mockResolvedValue(false)
    const ensureQueryData = vi.fn()

    const redirectError = await captureRedirect(() =>
      requireAuthenticated({
        context: { queryClient: { ensureQueryData } as unknown as QueryClient },
        location: createLocation('/chat/thread-1'),
      }),
    )

    expect(isRedirect(redirectError)).toBe(true)
    if (!isRedirect(redirectError)) {
      throw new Error('expected redirect')
    }
    expect(redirectError.options.to).toBe('/login')
    expect(redirectError.options.search).toEqual({ redirect: '/chat/thread-1' })
    expect(ensureQueryData).not.toHaveBeenCalled()
  })

  it('已登录时预热当前用户缓存，不重复发起第二份请求', async () => {
    vi.mocked(ensureAuthSession).mockResolvedValue(true)
    const ensureQueryData = vi.fn().mockResolvedValue({ publicId: 'u-1' })

    await requireAuthenticated({
      context: { queryClient: { ensureQueryData } as unknown as QueryClient },
      location: createLocation('/chat/new'),
    })

    expect(ensureQueryData).toHaveBeenCalledTimes(1)
    expect(ensureQueryData).toHaveBeenCalledWith(currentUserQueryOptions)
    expect(currentUserQueryOptions.queryKey).toEqual(queryKeys.auth.currentUser)
  })
})

describe('redirectAuthenticatedUser', () => {
  beforeEach(() => {
    vi.mocked(ensureAuthSession).mockReset()
  })

  it('已登录访问登录页时替换跳转到新对话页', async () => {
    vi.mocked(ensureAuthSession).mockResolvedValue(true)

    const redirectError = await captureRedirect(redirectAuthenticatedUser)

    expect(isRedirect(redirectError)).toBe(true)
    if (!isRedirect(redirectError)) {
      throw new Error('expected redirect')
    }
    expect(redirectError.options.to).toBe('/chat/new')
    expect(redirectError.options.replace).toBe(true)
  })

  it('未登录时放行登录页', async () => {
    vi.mocked(ensureAuthSession).mockResolvedValue(false)

    await expect(redirectAuthenticatedUser()).resolves.toBeUndefined()
  })
})
