import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useForm, type FieldErrors } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { AlertCircle } from 'lucide-react'

import { normalizeError } from '@/core/http'
import type { ModelConnection } from '@/features/models/api'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'

import {
  API_KEY_MAX,
  BASE_URL_MAX,
  createModelConnectionSchema,
  toModelConnectionPayload,
  type ModelConnectionFormValues,
} from '../model/model-connection-schema'
import { useModelConnectionCreate } from '../model/use-model-connections'
import { SettingsField } from './settings-field'

const BASE_URL_INVALID_CODE = 40214

/** 校验失败的聚焦顺序：接入地址最容易被浏览器凭据自动填充污染，优先让用户看到 */
const INVALID_FOCUS_ORDER = ['baseUrl', 'apiKey'] as const

export interface ModelConnectionFormProps {
  /** 由上层视图选定的 Provider，表单内不再提供下拉切换 */
  providerCode: string
  /** 创建成功后回传连接，父视图据此进入详情 */
  onCreated?: (connection: ModelConnection) => void
}

/** 接入表单：密钥只在请求体中出现，成功后立即从表单状态清空 */
export function ModelConnectionForm({ providerCode, onCreated }: ModelConnectionFormProps) {
  const { t } = useTranslation()
  const [formError, setFormError] = useState('')
  const { create, isCreating } = useModelConnectionCreate()
  const {
    register,
    handleSubmit,
    reset,
    setError,
    setFocus,
    formState: { errors },
  } = useForm<ModelConnectionFormValues>({
    resolver: zodResolver(createModelConnectionSchema(t)),
    defaultValues: {
      providerCode,
      baseUrl: '',
      apiKey: '',
    },
  })

  const focusFirstInvalidField = (invalidErrors: FieldErrors<ModelConnectionFormValues>): void => {
    const firstInvalidField = INVALID_FOCUS_ORDER.find((field) => invalidErrors[field])
    if (firstInvalidField) {
      setFocus(firstInvalidField)
    }
  }

  const submit = handleSubmit(async (values) => {
    setFormError('')
    try {
      const created = await create(toModelConnectionPayload(values))
      // 地址与凭证清空；明文不再停留于组件状态
      reset({ providerCode, baseUrl: '', apiKey: '' })
      onCreated?.(created)
    } catch (error) {
      const apiError = normalizeError(error)
      if (apiError.code === BASE_URL_INVALID_CODE) {
        setError('baseUrl', { type: 'server', message: apiError.message })
      } else {
        setFormError(apiError.message)
      }
    }
  }, focusFirstInvalidField)

  const isDisabled = isCreating

  return (
    <form
      className="flex flex-col gap-5"
      noValidate
      autoComplete="off"
      onSubmit={(event) => void submit(event)}
    >
      <SettingsField
        id="settings-model-base-url"
        label={t('settings.model.baseUrl')}
        hint={t('settings.model.baseUrlHint')}
        error={errors.baseUrl?.message}
      >
        <Input
          id="settings-model-base-url"
          type="url"
          autoComplete="off"
          maxLength={BASE_URL_MAX}
          placeholder={t('settings.model.baseUrlPlaceholder')}
          disabled={isDisabled}
          aria-invalid={Boolean(errors.baseUrl)}
          aria-describedby={errors.baseUrl ? 'settings-model-base-url-error' : undefined}
          {...register('baseUrl')}
        />
      </SettingsField>

      <SettingsField
        id="settings-model-api-key"
        label={t('settings.model.apiKey')}
        hint={t('settings.model.apiKeyHint')}
        error={errors.apiKey?.message}
      >
        <Input
          id="settings-model-api-key"
          type="password"
          autoComplete="new-password"
          maxLength={API_KEY_MAX}
          placeholder={t('settings.model.apiKeyPlaceholder')}
          disabled={isDisabled}
          aria-invalid={Boolean(errors.apiKey)}
          aria-describedby={errors.apiKey ? 'settings-model-api-key-error' : undefined}
          {...register('apiKey')}
        />
      </SettingsField>

      <p className="rounded-[var(--cds-panel-radius)] border border-border bg-surface px-3 py-2 text-xs leading-relaxed text-muted-foreground">
        {t('settings.model.securityNotice')}
      </p>

      {formError ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-[var(--cds-panel-radius)] border border-destructive/25 bg-destructive/10 px-3 py-2 text-xs text-destructive"
        >
          <AlertCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <p className="leading-relaxed">{formError}</p>
        </div>
      ) : null}

      <div className="flex justify-end">
        <Button type="submit" disabled={isDisabled}>
          {isCreating ? t('settings.model.adding') : t('settings.model.add')}
        </Button>
      </div>
    </form>
  )
}
