import { z } from 'zod'
import { createFileRoute } from '@tanstack/react-router'
import { FeedbackPage } from '@/features/feedback/components/feedback-page'

const feedbackSearchSchema = z.object({
  page: z.number().int().min(1).catch(1),
  size: z.number().int().min(1).max(100).catch(20),
  rating: z.enum(['', 'UP', 'DOWN']).catch(''),
  reasonCode: z
    .enum(['', 'INACCURATE', 'OFF_TOPIC', 'INCOMPLETE', 'FORMAT', 'UNSAFE', 'OTHER'])
    .catch(''),
  userId: z.string().max(36).catch(''),
  threadId: z.string().max(64).catch(''),
  from: z.string().max(10).catch(''),
  to: z.string().max(10).catch(''),
})

export const Route = createFileRoute('/_authenticated/feedback/')({
  validateSearch: feedbackSearchSchema,
  component: FeedbackPage,
})
