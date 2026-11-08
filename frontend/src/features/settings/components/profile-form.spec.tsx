import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/core/http'
import type { UserProfile } from '@/features/auth/api'

import { ProfileForm } from './profile-form'

const { updateProfileMock } = vi.hoisted(() => ({ updateProfileMock: vi.fn() }))

vi.mock('@/features/auth/api', () => ({ updateProfile: updateProfileMock }))

const profile: UserProfile = {
  publicId: 'user-1',
  username: 'tester',
  displayName: 'Tester',
  email: null,
  bio: null,
  roles: ['USER'],
  status: 'ACTIVE',
  createdAt: '2026-10-01T00:00:00Z',
  updatedAt: '2026-10-01T00:00:00Z',
}

const renderForm = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  render(
    <QueryClientProvider client={queryClient}>
      <ProfileForm profile={profile} />
    </QueryClientProvider>,
  )
}

describe('ProfileForm', () => {
  it('保存成功时提交 trim 后的资料并回写服务端返回值', async () => {
    updateProfileMock.mockResolvedValueOnce({ ...profile, displayName: 'Alice' })
    const user = userEvent.setup()
    renderForm()

    const displayName = screen.getByLabelText('显示名称')
    await user.clear(displayName)
    await user.type(displayName, '  Alice  ')
    await user.click(screen.getByRole('button', { name: '保存更改' }))

    await waitFor(() => {
      expect(updateProfileMock).toHaveBeenCalledWith(
        {
          displayName: 'Alice',
          email: null,
          bio: null,
        },
        expect.anything(),
      )
    })
    await waitFor(() => {
      expect(screen.getByLabelText('显示名称')).toHaveValue('Alice')
    })
  })

  it('显示名称为空时在字段上提示且不调用接口', async () => {
    const user = userEvent.setup()
    renderForm()

    await user.clear(screen.getByLabelText('显示名称'))
    await user.click(screen.getByRole('button', { name: '保存更改' }))

    expect(await screen.findByText('此项为必填。')).toBeInTheDocument()
    expect(updateProfileMock).not.toHaveBeenCalled()
  })

  it('邮箱冲突按业务码映射到邮箱字段', async () => {
    updateProfileMock.mockRejectedValueOnce(
      new ApiError('邮箱已被其他账号使用', { code: 40104, status: 409 }),
    )
    const user = userEvent.setup()
    renderForm()

    await user.type(screen.getByLabelText('邮箱'), 'used@example.com')
    await user.click(screen.getByRole('button', { name: '保存更改' }))

    expect(await screen.findByText('邮箱已被其他账号使用')).toBeInTheDocument()
    expect(updateProfileMock).toHaveBeenCalledTimes(1)
  })
})
