import { z } from 'zod'
import { createFileRoute } from '@tanstack/react-router'
import { AuditLogsPage } from '@/features/audit-logs/components/audit-logs-page'

const auditLogsSearchSchema = z.object({
  page: z.number().int().min(1).catch(1),
  size: z.number().int().min(1).max(100).catch(20),
  event: z.string().catch(''),
  username: z.string().max(64).catch(''),
})

export const Route = createFileRoute('/_authenticated/audit-logs/')({
  validateSearch: auditLogsSearchSchema,
  component: AuditLogsPage,
})
