import { z } from 'zod'
import { createFileRoute } from '@tanstack/react-router'
import { ModelsPage } from '@/features/models/components/models-page'

const modelsSearchSchema = z.object({
  page: z.number().int().min(1).catch(1),
  size: z.number().int().min(1).max(100).catch(20),
  keyword: z.string().max(64).catch(''),
  provider: z.string().max(32).catch(''),
  enabled: z.enum(['', 'true', 'false']).catch(''),
})

export const Route = createFileRoute('/_authenticated/models/')({
  validateSearch: modelsSearchSchema,
  component: ModelsPage,
})
