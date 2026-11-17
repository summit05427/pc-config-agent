import { useTranslation } from 'react-i18next'
import { useNavigate } from '@tanstack/react-router'

import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/shared/ui/select'
import { Button } from '@/shared/ui/button'
import type { ModelCatalogItem } from '@/features/models/api'
import { ROUTE_PATHS } from '@/routes/paths'

/** Radix Select 不接受空值，用内部哨兵值表示 Auto，对上层仍保持 null */
const AUTO_VALUE = '__auto__'
/** 菜单内的导航项，不参与模型选择 */
const ADD_MODEL_VALUE = '__add_model__'

export interface ModelSelectorProps {
  readonly models: readonly ModelCatalogItem[]
  /** null 表示 Auto（平台默认） */
  readonly modelKey: string | null
  readonly isLoading?: boolean
  readonly disabled?: boolean
  readonly onChange: (modelKey: string | null) => void
}

/**
 * 会话模型选择器。
 *
 * 目录里找不到当前 key 时退回原始值，避免触发器显示空白；选择结果由上层
 * 负责持久化与失败回滚，组件只做展示与转发。
 */
export function ModelSelector({
  models,
  modelKey,
  isLoading = false,
  disabled = false,
  onChange,
}: ModelSelectorProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  // 纯 BYOK 目录里没有平台模型，此时「自动（平台默认）」是误导项；
  // 保留 Auto 语义（由后端选择用户可用的 BYOK 模型），但改名为「自动（我的密钥）」
  const hasManagedModel = models.some((model) => model.credentialSource !== 'BYOK')
  const autoLabel = hasManagedModel ? t('chat.model.auto') : t('chat.model.autoByok')

  // 触发器展示当前选中的模型名；目录里找不到该 key 时退回原始 key，避免出现空白
  const currentModel = models.find((model) => model.modelKey === modelKey)
  const triggerLabel =
    modelKey === null
      ? t('chat.model.autoShort')
      : (currentModel?.displayName ?? modelKey)

  const handleValueChange = (value: string): void => {
    if (value === ADD_MODEL_VALUE) {
      void navigate({ to: ROUTE_PATHS.settingsSection, params: { section: 'model' } })
      return
    }
    onChange(value === AUTO_VALUE ? null : value)
  }

  // 目录为空说明平台托管已关闭且用户还没接入任何可用密钥：直接引导配置，
  // 不展示 Auto 或平台模型，避免用户选到不可用的条目
  if (models.length === 0 && !isLoading) {
    return (
      <Button
        variant="outline"
        size="sm"
        onClick={() => void navigate({ to: ROUTE_PATHS.settingsSection, params: { section: 'model' } })}
      >
        {t('chat.model.configure')}
      </Button>
    )
  }

  return (
    <Select
      value={modelKey ?? AUTO_VALUE}
      disabled={disabled || isLoading}
      onValueChange={handleValueChange}
    >
      <SelectTrigger
        id="chat-model-selector"
        size="sm"
        aria-label={t('chat.model.label')}
        className="h-[var(--control-height-sm)] max-w-[12rem] rounded-[var(--cds-radius-btn-xs)] border-border bg-surface transition-[background-color,border-color,box-shadow] duration-150 hover:border-border-strong hover:bg-muted"
      >
        <SelectValue>{triggerLabel}</SelectValue>
      </SelectTrigger>

      <SelectContent position="popper">
        <SelectItem value={AUTO_VALUE}>{autoLabel}</SelectItem>
        {models.map((model) => (
          <SelectItem key={model.modelKey} value={model.modelKey}>
            <span className="flex min-w-0 flex-col">
              <span className="flex items-center gap-1.5">
                <span className="truncate">{model.displayName}</span>
                {model.credentialSource === 'BYOK' ? (
                  <span className="shrink-0 rounded-sm bg-muted px-1 py-0.5 text-[0.625rem] text-muted-foreground">
                    {t('chat.model.sourceByok')}
                  </span>
                ) : null}
              </span>
              <span className="truncate text-xs text-muted-foreground">{model.modelKey}</span>
            </span>
          </SelectItem>
        ))}
        <SelectSeparator />
        <SelectItem value={ADD_MODEL_VALUE}>{t('chat.model.add')}</SelectItem>
      </SelectContent>
    </Select>
  )
}
