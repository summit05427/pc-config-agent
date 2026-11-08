import { z } from 'zod'
import { createFileRoute } from '@tanstack/react-router'
import { UsagePage } from '@/features/usage/components/usage-page'

const usageSearchSchema = z.object({
  page: z.number().int().min(1).catch(1),
  size: z.number().int().min(1).max(100).catch(20),
  userId: z.string().max(36).catch(''),
  provider: z.string().max(32).catch(''),
  modelKey: z.string().max(64).catch(''),
  credentialSource: z.enum(['', 'MANAGED', 'BYOK']).catch(''),
  costStatus: z
    .enum(['', 'ESTIMATED', 'UNKNOWN', 'BYOK_NOT_BILLED'])
    .catch(''),
  status: z.enum(['', 'success', 'failure']).catch(''),
  from: z.string().max(10).catch(''),
  to: z.string().max(10).catch(''),
  order: z.enum(['desc', 'asc']).catch('desc'),
})

export const Route = createFileRoute('/_authenticated/usage/')({
  validateSearch: usageSearchSchema,
  component: UsagePage,
})
