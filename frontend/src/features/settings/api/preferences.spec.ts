import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/core/http', () => ({
  http: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

import { http } from '@/core/http'

import { getPreferences, updatePreferences } from './preferences'
import type { PreferenceUpdatePayload } from './preferences'

describe('preferences api', () => {
  const preferences = {
    instructions: null,
    replyLanguage: 'auto',
    responseStyle: 'balanced',
    useHistory: true,
    updatedAt: null,
  }

  beforeEach(() => {
    vi.mocked(http.get).mockResolvedValue(preferences)
    vi.mocked(http.put).mockResolvedValue(preferences)
  })

  it('读取偏好命中 /users/me/preferences', async () => {
    await expect(getPreferences()).resolves.toEqual(preferences)
    expect(http.get).toHaveBeenCalledWith('/users/me/preferences')
  })

  it('保存偏好以 PUT 全量提交并回读服务端值', async () => {
    const payload: PreferenceUpdatePayload = {
      instructions: '先给结论',
      replyLanguage: 'zh-CN',
      responseStyle: 'concise',
      useHistory: false,
    }

    await expect(updatePreferences(payload)).resolves.toEqual(preferences)
    expect(http.put).toHaveBeenCalledWith('/users/me/preferences', payload)
  })
})
