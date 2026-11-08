import { z } from 'zod'
import { createFileRoute } from '@tanstack/react-router'
import { AdminUsersPage } from '@/features/admin-users/components/admin-users-page'

const usersSearchSchema = z.object({
  page: z.number().int().min(1).catch(1),
  size: z.number().int().min(1).max(100).catch(20),
  keyword: z.string().max(64).catch(''),
  status: z.enum(['', 'ACTIVE', 'DISABLED']).catch(''),
})

export const Route = createFileRoute('/_authenticated/users/')({
  validateSearch: usersSearchSchema,
  component: AdminUsersPage,
})
