import type { TFunction } from 'i18next'

/**
 * 需求向导里的单个选项。
 *
 * `labelKey` 同时承担两个用途：面板按钮文案，以及最终描述里的措辞，
 * 这样面板展示与生成的 prompt 永远不会出现两套说法。
 */
export interface QuickPromptOption {
  /** 稳定 ID，作为选择集合的键，不参与展示 */
  readonly id: string
  readonly labelKey: string
}

export interface QuickPromptGroup {
  readonly id: string
  readonly labelKey: string
  /**
   * 互斥组（预算、分辨率、品牌组合）只允许保留一个选项：
   * 避免出现「5000 元以内 + 2 万元」这类自相矛盾的需求。
   */
  readonly isExclusive: boolean
  readonly options: readonly QuickPromptOption[]
}

/**
 * 面向 PC 配置推荐的选项表。
 *
 * 普通用户往往说不清预算区间、用途权重和品牌倾向，这里把常见维度提前枚举，
 * 用户只需累积勾选，由 `buildQuickPrompt` 拼成一段可直接发送的需求描述。
 */
export const QUICK_PROMPT_GROUPS: readonly QuickPromptGroup[] = [
  {
    id: 'budget',
    labelKey: 'chat.quickPick.groups.budget',
    isExclusive: true,
    options: [
      { id: 'budget-under-5000', labelKey: 'chat.quickPick.options.budgetUnder5000' },
      { id: 'budget-5000-8000', labelKey: 'chat.quickPick.options.budget5000to8000' },
      { id: 'budget-8000-12000', labelKey: 'chat.quickPick.options.budget8000to12000' },
      { id: 'budget-12000-20000', labelKey: 'chat.quickPick.options.budget12000to20000' },
      { id: 'budget-above-20000', labelKey: 'chat.quickPick.options.budgetAbove20000' },
    ],
  },
  {
    id: 'purpose',
    labelKey: 'chat.quickPick.groups.purpose',
    isExclusive: false,
    options: [
      { id: 'purpose-aaa', labelKey: 'chat.quickPick.options.purposeAaa' },
      { id: 'purpose-esports', labelKey: 'chat.quickPick.options.purposeEsports' },
      { id: 'purpose-video', labelKey: 'chat.quickPick.options.purposeVideo' },
      { id: 'purpose-render', labelKey: 'chat.quickPick.options.purposeRender' },
      { id: 'purpose-design', labelKey: 'chat.quickPick.options.purposeDesign' },
      { id: 'purpose-dev', labelKey: 'chat.quickPick.options.purposeDev' },
      { id: 'purpose-ai', labelKey: 'chat.quickPick.options.purposeAi' },
      { id: 'purpose-data', labelKey: 'chat.quickPick.options.purposeData' },
      { id: 'purpose-vm', labelKey: 'chat.quickPick.options.purposeVm' },
      { id: 'purpose-office', labelKey: 'chat.quickPick.options.purposeOffice' },
      { id: 'purpose-stream', labelKey: 'chat.quickPick.options.purposeStream' },
      { id: 'purpose-media', labelKey: 'chat.quickPick.options.purposeMedia' },
      { id: 'purpose-storage', labelKey: 'chat.quickPick.options.purposeStorage' },
    ],
  },
  {
    id: 'priority',
    labelKey: 'chat.quickPick.groups.priority',
    isExclusive: false,
    options: [
      { id: 'priority-gpu', labelKey: 'chat.quickPick.options.priorityGpu' },
      { id: 'priority-cpu', labelKey: 'chat.quickPick.options.priorityCpu' },
      { id: 'priority-memory', labelKey: 'chat.quickPick.options.priorityMemory' },
      { id: 'priority-ssd', labelKey: 'chat.quickPick.options.prioritySsd' },
      { id: 'priority-quiet', labelKey: 'chat.quickPick.options.priorityQuiet' },
      { id: 'priority-value', labelKey: 'chat.quickPick.options.priorityValue' },
    ],
  },
  {
    id: 'display',
    labelKey: 'chat.quickPick.groups.display',
    isExclusive: true,
    options: [
      { id: 'display-1080p', labelKey: 'chat.quickPick.options.display1080' },
      { id: 'display-2k', labelKey: 'chat.quickPick.options.display2k' },
      { id: 'display-4k', labelKey: 'chat.quickPick.options.display4k' },
      { id: 'display-ultrawide', labelKey: 'chat.quickPick.options.displayUltrawide' },
      { id: 'display-dual', labelKey: 'chat.quickPick.options.displayDual' },
      { id: 'display-keep', labelKey: 'chat.quickPick.options.displayKeep' },
    ],
  },
  {
    id: 'brand',
    labelKey: 'chat.quickPick.groups.brand',
    isExclusive: true,
    options: [
      { id: 'brand-any', labelKey: 'chat.quickPick.options.brandAny' },
      { id: 'brand-intel-nvidia', labelKey: 'chat.quickPick.options.brandIntelNvidia' },
      { id: 'brand-amd-all', labelKey: 'chat.quickPick.options.brandAmdAll' },
      { id: 'brand-amd-nvidia', labelKey: 'chat.quickPick.options.brandAmdNvidia' },
      { id: 'brand-nvidia', labelKey: 'chat.quickPick.options.brandNvidia' },
    ],
  },
  {
    id: 'storage',
    labelKey: 'chat.quickPick.groups.storage',
    isExclusive: false,
    options: [
      { id: 'storage-1t', labelKey: 'chat.quickPick.options.storage1t' },
      { id: 'storage-2t', labelKey: 'chat.quickPick.options.storage2t' },
      { id: 'storage-4t', labelKey: 'chat.quickPick.options.storage4t' },
      { id: 'storage-hdd', labelKey: 'chat.quickPick.options.storageHdd' },
      { id: 'storage-m2', labelKey: 'chat.quickPick.options.storageM2' },
    ],
  },
  {
    id: 'form',
    labelKey: 'chat.quickPick.groups.form',
    isExclusive: false,
    options: [
      { id: 'form-quiet', labelKey: 'chat.quickPick.options.formQuiet' },
      { id: 'form-white', labelKey: 'chat.quickPick.options.formWhite' },
      { id: 'form-itx', labelKey: 'chat.quickPick.options.formItx' },
      { id: 'form-rgb', labelKey: 'chat.quickPick.options.formRgb' },
      { id: 'form-window', labelKey: 'chat.quickPick.options.formWindow' },
      { id: 'form-air', labelKey: 'chat.quickPick.options.formAir' },
      { id: 'form-aio', labelKey: 'chat.quickPick.options.formAio' },
      { id: 'form-no-rgb', labelKey: 'chat.quickPick.options.formNoRgb' },
    ],
  },
  {
    id: 'connectivity',
    labelKey: 'chat.quickPick.groups.connectivity',
    isExclusive: false,
    options: [
      { id: 'conn-wifi7', labelKey: 'chat.quickPick.options.connWifi7' },
      { id: 'conn-25g', labelKey: 'chat.quickPick.options.conn25g' },
      { id: 'conn-bt', labelKey: 'chat.quickPick.options.connBt' },
      { id: 'conn-dual', labelKey: 'chat.quickPick.options.connDual' },
      { id: 'conn-usb', labelKey: 'chat.quickPick.options.connUsb' },
      { id: 'conn-thunderbolt', labelKey: 'chat.quickPick.options.connThunderbolt' },
    ],
  },
  {
    id: 'extras',
    labelKey: 'chat.quickPick.groups.extras',
    isExclusive: false,
    options: [
      { id: 'extras-peripherals', labelKey: 'chat.quickPick.options.extrasPeripherals' },
      { id: 'extras-monitor', labelKey: 'chat.quickPick.options.extrasMonitor' },
      { id: 'extras-os', labelKey: 'chat.quickPick.options.extrasOs' },
      { id: 'extras-upgrade', labelKey: 'chat.quickPick.options.extrasUpgrade' },
      { id: 'extras-service', labelKey: 'chat.quickPick.options.extrasService' },
      { id: 'extras-onsite', labelKey: 'chat.quickPick.options.extrasOnsite' },
      { id: 'extras-migration', labelKey: 'chat.quickPick.options.extrasMigration' },
    ],
  },
]

/**
 * 把勾选结果拼成一段完整需求描述。
 *
 * 分组顺序固定为 `QUICK_PROMPT_GROUPS` 的顺序，空分组直接跳过；
 * 分隔符与结尾句全部走 i18n，保证中英文描述都自然。
 * 未选择任何选项时返回空串，由调用方保持确认按钮禁用。
 */
export const buildQuickPrompt = (selectedIds: ReadonlySet<string>, t: TFunction): string => {
  const lines: string[] = []

  for (const group of QUICK_PROMPT_GROUPS) {
    const labels = group.options
      .filter((option) => selectedIds.has(option.id))
      .map((option) => t(option.labelKey))
    if (labels.length === 0) {
      continue
    }
    lines.push(
      t('chat.quickPick.groupLine', {
        label: t(group.labelKey),
        value: labels.join(t('chat.quickPick.valueSeparator')),
      }),
    )
  }

  if (lines.length === 0) {
    return ''
  }
  return `${lines.join(t('chat.quickPick.groupSeparator'))}${t('chat.quickPick.promptTail')}`
}
