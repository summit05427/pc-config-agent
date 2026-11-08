import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Controller, useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertCircle } from 'lucide-react'
import { toast } from 'sonner'
import { z } from 'zod'

import { normalizeError } from '@/core/http'
import {
  updatePreferences,
  type PreferenceReplyLanguage,
  type PreferenceResponseStyle,
  type UserPreferences,
} from '@/features/settings/api'
import { queryKeys } from '@/shared/lib/query-keys'
import { Button } from '@/shared/ui/button'
import { Textarea } from '@/shared/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/ui/select'

import { SettingsField } from './settings-field'
import { SettingsToggleRow } from './settings-toggle-row'

const INSTRUCTIONS_MAX = 1000

interface AgentFormValues {
  instructions: string
  replyLanguage: PreferenceReplyLanguage
  responseStyle: PreferenceResponseStyle
  useHistory: boolean
}

type Translate = (key: string, options?: Record<string, unknown>) => string

const createAgentSchema = (t: Translate) =>
  z.object({
    instructions: z.string().max(INSTRUCTIONS_MAX, {
      message: t('settings.errors.tooLong', { max: INSTRUCTIONS_MAX }),
    }),
    replyLanguage: z.enum(['auto', 'zh-CN', 'en-US']),
    responseStyle: z.enum(['concise', 'balanced', 'detailed']),
    useHistory: z.boolean(),
  })

const toFormValues = (preferences: UserPreferences): AgentFormValues => ({
  instructions: preferences.instructions ?? '',
  replyLanguage: preferences.replyLanguage,
  responseStyle: preferences.responseStyle,
  useHistory: preferences.useHistory,
})

const toNullable = (value: string): string | null => {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

/** Agent 偏好表单：服务端是唯一事实来源，保存后重置为服务端返回值并失效缓存 */
export function AgentForm({ preferences }: { preferences: UserPreferences }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [formError, setFormError] = useState('')
  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<AgentFormValues>({
    resolver: zodResolver(createAgentSchema(t)),
    defaultValues: toFormValues(preferences),
  })
  const mutation = useMutation({ mutationFn: updatePreferences })

  const submit = handleSubmit(async (values) => {
    setFormError('')
    try {
      const saved = await mutation.mutateAsync({
        instructions: toNullable(values.instructions),
        replyLanguage: values.replyLanguage,
        responseStyle: values.responseStyle,
        useHistory: values.useHistory,
      })
      reset(toFormValues(saved))
      await queryClient.invalidateQueries({ queryKey: queryKeys.settings.preferences })
      toast.success(t('settings.agent.saveSuccess'))
    } catch (error) {
      const apiError = normalizeError(error)
      // 偏好接口没有可归属到单一字段的业务码，统一用表单级错误条
      setFormError(apiError.message)
    }
  })

  return (
    <form className="flex flex-col gap-5" noValidate onSubmit={(event) => void submit(event)}>
      <SettingsField
        id="settings-agent-instructions"
        label={t('settings.agent.instructions')}
        hint={t('settings.agent.instructionsHint')}
        error={errors.instructions?.message}
      >
        <Textarea
          id="settings-agent-instructions"
          rows={5}
          maxLength={INSTRUCTIONS_MAX}
          placeholder={t('settings.agent.instructionsPlaceholder')}
          disabled={mutation.isPending}
          aria-invalid={Boolean(errors.instructions)}
          aria-describedby={errors.instructions ? 'settings-agent-instructions-error' : undefined}
          {...register('instructions')}
        />
      </SettingsField>

      <div className="grid gap-5 border-t border-border pt-6 sm:grid-cols-2">
        <Controller
          control={control}
          name="replyLanguage"
          render={({ field }) => (
            <SettingsField id="settings-agent-language" label={t('settings.agent.replyLanguage')}>
              <Select value={field.value} onValueChange={field.onChange} disabled={mutation.isPending}>
                <SelectTrigger id="settings-agent-language" size="sm" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent position="popper">
                  <SelectItem value="auto">{t('settings.agent.replyAuto')}</SelectItem>
                  <SelectItem value="zh-CN">{t('settings.agent.replyZh')}</SelectItem>
                  <SelectItem value="en-US">{t('settings.agent.replyEn')}</SelectItem>
                </SelectContent>
              </Select>
            </SettingsField>
          )}
        />

        <Controller
          control={control}
          name="responseStyle"
          render={({ field }) => (
            <SettingsField id="settings-agent-style" label={t('settings.agent.responseStyle')}>
              <Select value={field.value} onValueChange={field.onChange} disabled={mutation.isPending}>
                <SelectTrigger id="settings-agent-style" size="sm" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent position="popper">
                  <SelectItem value="concise">{t('settings.agent.styleConcise')}</SelectItem>
                  <SelectItem value="balanced">{t('settings.agent.styleBalanced')}</SelectItem>
                  <SelectItem value="detailed">{t('settings.agent.styleDetailed')}</SelectItem>
                </SelectContent>
              </Select>
            </SettingsField>
          )}
        />
      </div>

      <div className="border-t border-border pt-6">
        <Controller
          control={control}
          name="useHistory"
          render={({ field }) => (
            <SettingsToggleRow
              id="settings-agent-history"
              label={t('settings.agent.history')}
              description={t('settings.agent.historyHint')}
              checked={field.value}
              onCheckedChange={field.onChange}
              disabled={mutation.isPending}
            />
          )}
        />
      </div>

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
          {mutation.isPending
            ? t('settings.agent.saving')
            : formError
              ? t('settings.agent.saveFailed')
              : t('settings.agent.saveHint')}
        </p>
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? t('settings.agent.saving') : t('settings.agent.save')}
        </Button>
      </div>
    </form>
  )
}
