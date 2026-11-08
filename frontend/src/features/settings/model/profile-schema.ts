import { z } from 'zod'

import type { UserProfile } from '@/features/auth/api'

export interface ProfileFormValues {
  displayName: string
  email: string
  bio: string
}

type Translate = (key: string, options?: Record<string, unknown>) => string

const DISPLAY_NAME_MAX = 64
const EMAIL_MAX = 255
const BIO_MAX = 500

/**
 * 个人资料表单 Schema。
 *
 * 邮箱允许留空（服务端以 null 表示未绑定），填写时必须符合邮箱格式；
 * 长度上限与输入框 maxLength 保持同一组常量，避免两处数字漂移。
 */
export function createProfileSchema(t: Translate) {
  const tooLong = (max: number): string => t('settings.errors.tooLong', { max })

  return z.object({
    displayName: z
      .string()
      .trim()
      .min(1, { message: t('settings.errors.required') })
      .max(DISPLAY_NAME_MAX, { message: tooLong(DISPLAY_NAME_MAX) }),
    email: z
      .string()
      .trim()
      .max(EMAIL_MAX, { message: tooLong(EMAIL_MAX) })
      .refine((value) => value === '' || z.string().email().safeParse(value).success, {
        message: t('settings.errors.invalidEmail'),
      }),
    bio: z.string().max(BIO_MAX, { message: tooLong(BIO_MAX) }),
  })
}

/** 服务端资料转表单默认值，未设置字段统一成空字符串供受控输入使用 */
export const toProfileFormValues = (profile: UserProfile): ProfileFormValues => ({
  displayName: profile.displayName ?? profile.username,
  email: profile.email ?? '',
  bio: profile.bio ?? '',
})

export { BIO_MAX, DISPLAY_NAME_MAX, EMAIL_MAX }
