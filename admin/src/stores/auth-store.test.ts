import { beforeEach, describe, expect, it, vi } from 'vitest'

const sampleUser = {
  publicId: '018f2b3c-4d5e-7a6b-8c9d-0e1f2a3b4c5d',
  username: 'admin',
  roles: ['ADMIN'],
}

describe('useAuthStore', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('starts with an empty in-memory session', async () => {
    const { useAuthStore } = await import('./auth-store')

    expect(useAuthStore.getState().auth.accessToken).toBe('')
    expect(useAuthStore.getState().auth.user).toBeNull()
  })

  it('keeps the access token out of cookies and local storage', async () => {
    const { useAuthStore } = await import('./auth-store')
    useAuthStore.getState().auth.setAccessToken('memory-token')

    expect(useAuthStore.getState().auth.accessToken).toBe('memory-token')
    expect(document.cookie).not.toContain('memory-token')
    expect(localStorage.getItem('memory-token')).toBeNull()
  })

  it('stores the signed-in user with roles', async () => {
    const { useAuthStore } = await import('./auth-store')
    useAuthStore.getState().auth.setUser(sampleUser)

    expect(useAuthStore.getState().auth.user).toEqual(sampleUser)
  })

  it('setSession updates user and token together', async () => {
    const { useAuthStore } = await import('./auth-store')
    useAuthStore
      .getState()
      .auth.setSession({ user: sampleUser, accessToken: 'session-token' })

    expect(useAuthStore.getState().auth.user).toEqual(sampleUser)
    expect(useAuthStore.getState().auth.accessToken).toBe('session-token')
  })

  it('reset clears user and access token', async () => {
    const { useAuthStore } = await import('./auth-store')
    useAuthStore
      .getState()
      .auth.setSession({ user: sampleUser, accessToken: 'to-clear' })

    useAuthStore.getState().auth.reset()

    expect(useAuthStore.getState().auth.user).toBeNull()
    expect(useAuthStore.getState().auth.accessToken).toBe('')
  })

  it('hasRole only matches roles granted to the user', async () => {
    const { hasRole } = await import('./auth-store')

    expect(hasRole(sampleUser, 'ADMIN')).toBe(true)
    expect(hasRole(sampleUser, 'USER')).toBe(false)
    expect(hasRole(null, 'ADMIN')).toBe(false)
  })
})
