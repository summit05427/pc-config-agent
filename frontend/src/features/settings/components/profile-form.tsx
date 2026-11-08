import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useForm, useWatch } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertCircle } from 'lucide-react'

import { normalizeError } from '@/core/http'
import { updateProfile, type UserProfile } from '@/features/auth/api'
import { queryKeys } from '@/shared/lib/query-keys'
import { Avatar, AvatarFallback } from '@/shared/ui/avatar'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'
import { Textarea } from '@/shared/ui/textarea'
import { toast } from 'sonner'

import {
  BIO_MAX,
  DISPLAY_NAME_MAX,
  EMAIL_MAX,
  createProfileSchema,
  toProfileFormValues,
  type ProfileFormValues,
} from '../model/profile-schema'
import { SettingsField } from './settings-field'

/** 邮箱冲突是唯一能确定归属字段的服务端业务码 */
const EMAIL_TAKEN_CODE = 40104

export interface ProfileFormProps {
  profile: UserProfile
}

const toNullable = (value: string): string | null => {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

/** 个人资料表单：保存成功回写表单并失效缓存，失败按业务码落到对应字段 */
export function ProfileForm({ profile }: ProfileFormProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [formError, setFormError] = useState('')
  const {
    register,
    control,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<ProfileFormValues>({
    resolver: zodResolver(createProfileSchema(t)),
    defaultValues: toProfileFormValues(profile),
  })
  const displayName = useWatch({ control, name: 'displayName' })
  const mutation = useMutation({ mutationFn: updateProfile })

  const isSaving = mutation.isPending
  const avatarName = displayName?.trim() || profile.username || t('settings.profile.guestName')
  const initials = avatarName.slice(0, 2).toUpperCase()

  const submit = handleSubmit(async (values) => {
    setFormError('')
    try {
      const saved = await mutation.mutateAsync({
        displayName: values.displayName.trim(),
        email: toNullable(values.email),
        bio: toNullable(values.bio),
      })
      reset(toProfileFormValues(saved))
      await queryClient.invalidateQueries({ queryKey: queryKeys.settings.profile })
      toast.success(t('settings.profile.saveSuccess'))
    } catch (error) {
      const apiError = normalizeError(error)
      if (apiError.code === EMAIL_TAKEN_CODE) {
        setFormError('')
        // 邮箱冲突只回填到字段，避免顶部错误条与字段错误重复提示同一件事
        setError('email', { type: 'server', message: apiError.message })
      } else {
        setFormError(apiError.message)
      }
    }
  })

  return (
    <form className="flex flex-col gap-5" noValidate onSubmit={(event) => void submit(event)}>
      <div className="flex items-center gap-4">
        <Avatar size="lg" className="bg-primary/10">
          <AvatarFallback className="bg-transparent text-sm font-semibold text-primary">
            {initials}
          </AvatarFallback>
        </Avatar>

        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-foreground">{avatarName}</p>
          <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
            {t('settings.profile.avatarHint')}
          </p>
        </div>

        <Button variant="outline" size="sm" className="shrink-0" disabled>
          {t('settings.profile.changeAvatar')}
        </Button>
      </div>

      <div className="grid gap-5 sm:grid-cols-2">
        <SettingsField
          id="settings-profile-name"
          label={t('settings.profile.displayName')}
          error={errors.displayName?.message}
        >
          <Input
            id="settings-profile-name"
            placeholder={t('settings.profile.displayNamePlaceholder')}
            autoComplete="name"
            maxLength={DISPLAY_NAME_MAX}
            disabled={isSaving}
            aria-invalid={Boolean(errors.displayName)}
            aria-describedby={errors.displayName ? 'settings-profile-name-error' : undefined}
            {...register('displayName')}
          />
        </SettingsField>

        <SettingsField
          id="settings-profile-email"
          label={t('settings.profile.email')}
          error={errors.email?.message}
        >
          <Input
            id="settings-profile-email"
            type="email"
            placeholder={t('settings.profile.emailPlaceholder')}
            autoComplete="email"
            maxLength={EMAIL_MAX}
            disabled={isSaving}
            aria-invalid={Boolean(errors.email)}
            aria-describedby={errors.email ? 'settings-profile-email-error' : undefined}
            {...register('email')}
          />
        </SettingsField>
      </div>

      <SettingsField
        id="settings-profile-bio"
        label={t('settings.profile.bio')}
        error={errors.bio?.message}
      >
        <Textarea
          id="settings-profile-bio"
          rows={4}
          placeholder={t('settings.profile.bioPlaceholder')}
          maxLength={BIO_MAX}
          disabled={isSaving}
          aria-invalid={Boolean(errors.bio)}
          aria-describedby={errors.bio ? 'settings-profile-bio-error' : undefined}
          {...register('bio')}
        />
      </SettingsField>

      {formError ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-[var(--cds-panel-radius)] border border-destructive/25 bg-destructive/10 px-3 py-2 text-xs text-destructive"
        >
          <AlertCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <p className="leading-relaxed">{formError}</p>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-end gap-3">
        <p role="status" className="text-xs leading-relaxed text-muted-foreground">
          {isSaving
            ? t('settings.profile.saving')
            : formError
              ? t('settings.profile.saveFailed')
              : t('settings.profile.saveHint')}
        </p>
        <Button type="submit" disabled={isSaving}>
          {isSaving ? t('settings.profile.saving') : t('settings.profile.save')}
        </Button>
      </div>
    </form>
  )
}
