import { z } from 'zod'
import { createFileRoute, redirect } from '@tanstack/react-router'
import { ensureSession } from '@/features/auth/api/auth-api'
import { hasRole } from '@/stores/auth-store'
import { SignIn } from '@/features/auth/sign-in'

const searchSchema = z.object({
  redirect: z.string().optional(),
})

export const Route = createFileRoute('/(auth)/sign-in')({
  validateSearch: searchSchema,
  // 已登录且具备 ADMIN 角色时不再停留在登录页
  beforeLoad: async () => {
    const user = await ensureSession()
    if (user && hasRole(user, 'ADMIN')) {
      throw redirect({
        to: '/users',
        search: { page: 1, size: 20, keyword: '', status: '' },
      })
    }
  },
  component: SignIn,
})
