import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { KeyRound, ShieldCheck, Trash2 } from 'lucide-react'

import { normalizeError } from '@/core/http'
import type {
  ModelCatalogItem,
  ModelConnection,
  ModelConnectionUpdatePayload,
} from '@/features/models/api'
import { formatDateTime } from '@/shared/lib/format'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/shared/ui/alert-dialog'
import { Button } from '@/shared/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/shared/ui/dialog'
import { Input } from '@/shared/ui/input'

import {
  API_KEY_MAX,
  BASE_URL_MAX,
  createModelCredentialSchema,
  toModelCredentialPayload,
  type ModelCredentialFormValues,
} from '../model/model-connection-schema'
import { ModelCatalogList } from './model-catalog-list'
import { ModelConnectionStatus } from './model-connection-status'
import { ModelProviderLogo } from './model-provider-logo'
import { ModelViewHeader } from './model-view-header'
import { SettingsField } from './settings-field'

export interface ModelConnectionDetailProps {
  connection: ModelConnection
  models: readonly ModelCatalogItem[]
  /** 验证、轮换或删除进行中，禁用操作按钮避免重复提交 */
  isBusy: boolean
  onBack: () => void
  onVerify: () => void
  /** 轮换凭证；失败时抛出 ApiError，由弹窗内联提示 */
  onRotate: (payload: ModelConnectionUpdatePayload) => Promise<void>
  onDelete: () => void
}

/** 已接入供应商详情：凭证事实、验证/轮换/删除操作与可用模型 */
export function ModelConnectionDetail({
  connection,
  models,
  isBusy,
  onBack,
  onVerify,
  onRotate,
  onDelete,
}: ModelConnectionDetailProps) {
  const { t } = useTranslation()
  const [isRotateOpen, setRotateOpen] = useState(false)

  const facts = [
    {
      label: t('settings.model.baseUrl'),
      value: connection.baseUrl || t('settings.model.detail.baseUrlDefault'),
      isMono: true,
    },
    {
      label: t('settings.model.detail.credential'),
      value: connection.credential?.maskedHint ?? t('settings.model.detail.credentialEmpty'),
      isMono: true,
    },
    {
      label: t('settings.model.detail.createdAt'),
      value: formatDateTime(connection.createdAt),
      isMono: false,
    },
    {
      label: t('settings.model.detail.lastVerifiedAt'),
      value: connection.lastVerifiedAt
        ? formatDateTime(connection.lastVerifiedAt)
        : t('settings.model.detail.neverVerified'),
      isMono: false,
    },
  ]

  return (
    <div className="flex flex-col gap-6">
      <ModelViewHeader
        backLabel={t('settings.model.back')}
        title={connection.providerName}
        description={t('settings.model.detail.description')}
        onBack={onBack}
        leading={
          <ModelProviderLogo
            providerCode={connection.provider}
            label={connection.providerName}
            size="md"
          />
        }
        badge={<ModelConnectionStatus connection={connection} />}
      />

      <section className="flex flex-col gap-4 rounded-[var(--cds-panel-radius)] border border-border bg-surface px-4 py-4">
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          {facts.map((fact) => (
            <div key={fact.label} className="min-w-0">
              <dt className="text-xs text-muted-foreground">{fact.label}</dt>
              <dd
                className={
                  fact.isMono
                    ? 'mt-0.5 truncate font-mono text-xs text-foreground'
                    : 'mt-0.5 truncate text-sm text-foreground'
                }
              >
                {fact.value}
              </dd>
            </div>
          ))}
        </dl>

        <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-4">
          <Button type="button" variant="outline" size="sm" disabled={isBusy} onClick={onVerify}>
            <ShieldCheck aria-hidden="true" />
            {isBusy ? t('settings.model.verifying') : t('settings.model.verify')}
          </Button>

          <RotateCredentialDialog
            connection={connection}
            isBusy={isBusy}
            open={isRotateOpen}
            onOpenChange={setRotateOpen}
            onRotate={onRotate}
          />

          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button type="button" variant="destructive" size="sm" disabled={isBusy}>
                <Trash2 aria-hidden="true" />
                {t('settings.model.delete')}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>{t('settings.model.delete')}</AlertDialogTitle>
                <AlertDialogDescription>
                  {t('settings.model.deleteConfirm', { provider: connection.providerName })}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
                <AlertDialogAction variant="destructive" onClick={onDelete}>
                  {t('settings.model.delete')}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h4 className="text-sm font-medium text-foreground">
            {t('settings.model.detail.modelsTitle')}
          </h4>
          <span className="tabular text-xs text-muted-foreground">
            {t('settings.model.detail.modelsCount', { count: models.length })}
          </span>
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">
          {t('settings.model.detail.modelsHint')}
        </p>
        <ModelCatalogList models={models} />
      </section>
    </div>
  )
}

interface RotateCredentialDialogProps {
  connection: ModelConnection
  isBusy: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
  onRotate: (payload: ModelConnectionUpdatePayload) => Promise<void>
}

/**
 * 轮换弹窗：旧凭证由服务端撤销，新密钥保存后自动验证。
 * 明文只停留在本地输入状态，提交成功或关闭弹窗都会清空。
 */
function RotateCredentialDialog({
  connection,
  isBusy,
  open,
  onOpenChange,
  onRotate,
}: RotateCredentialDialogProps) {
  const { t } = useTranslation()
  const [formError, setFormError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ModelCredentialFormValues>({
    resolver: zodResolver(createModelCredentialSchema(t)),
    defaultValues: { baseUrl: '', apiKey: '' },
  })

  const close = (): void => {
    // 明文不留在组件状态里，重开弹窗必须重新输入
    reset({ baseUrl: '', apiKey: '' })
    setFormError('')
    onOpenChange(false)
  }

  const submit = handleSubmit(async (values) => {
    setFormError('')
    setIsSubmitting(true)
    try {
      await onRotate(toModelCredentialPayload(values))
      close()
    } catch (error) {
      setFormError(normalizeError(error).message)
    } finally {
      setIsSubmitting(false)
    }
  })

  const isDisabled = isSubmitting || isBusy

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline" size="sm" disabled={isBusy}>
          <KeyRound aria-hidden="true" />
          {t('settings.model.rotate')}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('settings.model.rotateTitle')}</DialogTitle>
          <DialogDescription>
            {t('settings.model.rotateDescription', { provider: connection.providerName })}
          </DialogDescription>
        </DialogHeader>

        <form className="flex flex-col gap-4" noValidate onSubmit={(event) => void submit(event)}>
          <SettingsField
            id="settings-model-rotate-api-key"
            label={t('settings.model.apiKey')}
            hint={t('settings.model.apiKeyHint')}
            error={errors.apiKey?.message}
          >
            <Input
              id="settings-model-rotate-api-key"
              type="password"
              autoComplete="new-password"
              maxLength={API_KEY_MAX}
              placeholder={t('settings.model.apiKeyPlaceholder')}
              disabled={isDisabled}
              aria-invalid={Boolean(errors.apiKey)}
              aria-describedby={errors.apiKey ? 'settings-model-rotate-api-key-error' : undefined}
              {...register('apiKey')}
            />
          </SettingsField>

          <SettingsField
            id="settings-model-rotate-base-url"
            label={t('settings.model.baseUrl')}
            hint={t('settings.model.rotateBaseUrlHint')}
            error={errors.baseUrl?.message}
          >
            <Input
              id="settings-model-rotate-base-url"
              type="url"
              autoComplete="off"
              maxLength={BASE_URL_MAX}
              placeholder={t('settings.model.rotateBaseUrlPlaceholder')}
              disabled={isDisabled}
              aria-invalid={Boolean(errors.baseUrl)}
              aria-describedby={errors.baseUrl ? 'settings-model-rotate-base-url-error' : undefined}
              {...register('baseUrl')}
            />
          </SettingsField>

          {formError ? (
            <p role="alert" className="text-xs leading-relaxed text-destructive">
              {formError}
            </p>
          ) : null}

          <DialogFooter>
            <Button type="button" variant="outline" disabled={isDisabled} onClick={close}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={isDisabled}>
              {isSubmitting ? t('settings.model.rotating') : t('settings.model.rotateSubmit')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
