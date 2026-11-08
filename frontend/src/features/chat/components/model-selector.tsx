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

  // 触发器展示当前选中的模型名；目录里找不到该 key 时退回原始 key，避免出现空白
  const currentModel = models.find((model) => model.modelKey === modelKey)
  const triggerLabel =
    modelKey === null ? t('chat.model.autoShort') : (currentModel?.displayName ?? modelKey)

  const handleValueChange = (value: string): void => {
    if (value === ADD_MODEL_VALUE) {
      void navigate({ to: ROUTE_PATHS.settingsSection, params: { section: 'model' } })
      return
    }
    onChange(value === AUTO_VALUE ? null : value)
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
        <SelectItem value={AUTO_VALUE}>{t('chat.model.auto')}</SelectItem>
        {models.map((model) => (
          <SelectItem key={model.modelKey} value={model.modelKey}>
            <span className="flex min-w-0 flex-col">
              <span className="truncate">{model.displayName}</span>
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
