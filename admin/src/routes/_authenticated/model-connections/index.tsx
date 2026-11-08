import { z } from 'zod'
import { createFileRoute } from '@tanstack/react-router'
import { ConnectionsPage } from '@/features/model-connections/components/connections-page'

const connectionsSearchSchema = z.object({
  page: z.number().int().min(1).catch(1),
  size: z.number().int().min(1).max(100).catch(20),
  userId: z.string().max(36).catch(''),
  provider: z.string().max(32).catch(''),
  status: z.enum(['', 'ACTIVE', 'DELETED']).catch(''),
})

export const Route = createFileRoute('/_authenticated/model-connections/')({
  validateSearch: connectionsSearchSchema,
  component: ConnectionsPage,
})
