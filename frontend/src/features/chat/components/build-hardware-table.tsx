import { useTranslation } from 'react-i18next'

import type { BuildComponent } from '@/features/sessions/api'
import { cn } from '@/shared/lib/utils'
import { Badge } from '@/shared/ui/badge'

import { CATEGORY_LABEL_KEYS, isMockPrice } from './build-result-meta'

export interface BuildHardwareTableProps {
  readonly components: readonly BuildComponent[]
}

/**
 * 硬件清单表：类型 / 图片 / 产品 / 型号。
 *
 * 价格、未核验标识与购买跳转已按产品要求移除（价格只在汇总卡与预算模块展示）。
 * 列宽统一交给 colgroup，表头与单元格共用同一套网格，任何容器宽度下都严格对齐。
 */
export function BuildHardwareTable({ components }: BuildHardwareTableProps) {
  const { t } = useTranslation()

  if (components.length === 0) {
    return <p className="text-sm text-muted-foreground">{t('chat.build.emptyModel')}</p>
  }

  return (
    <table className="h-full w-full table-fixed border-collapse">
      {/* 列宽只在这里定义一次，避免 th 与 td 各写一套导致错位 */}
      <colgroup>
        <col className="w-[64px]" />
        <col className="w-12" />
        <col />
        <col className="w-[34%]" />
      </colgroup>
      <thead>
        <tr className="border-b border-border/60 text-[12px] text-muted-foreground">
          <th scope="col" className="pb-2 text-left font-medium">
            {t('chat.build.detailType')}
          </th>
          <th scope="col" className="pb-2 text-center font-medium">
            {t('chat.build.detailImage')}
          </th>
          <th scope="col" className="pb-2 pl-2 text-left font-medium">
            {t('chat.build.detailProduct')}
          </th>
          <th scope="col" className="pb-2 pl-2 text-left font-medium">
            {t('chat.build.detailModel')}
          </th>
        </tr>
      </thead>
      <tbody className="divide-y divide-border/40">
        {components.map((component) => {
          const categoryKey = CATEGORY_LABEL_KEYS[component.category]
          const categoryLabel = categoryKey ? t(categoryKey) : component.category
          const hasModel = Boolean(component.modelName)
          const mock = isMockPrice(component)
          const modelDetail = component.specSummary || component.title

          return (
            <tr key={component.category} className="align-middle">
              <td className="py-2 pr-1 text-[12.5px] whitespace-nowrap text-muted-foreground">
                {categoryLabel}
              </td>
              <td className="py-2 text-center">
                {component.imageUrl ? (
                  // 商品图多为白底：亮色 multiply 让白底融入卡片；暗色 invert+hue-rotate
                  // 反转明度保留色相，再 screen 滤掉黑底，避免白方块糊在深色卡面上
                  <img
                    src={component.imageUrl}
                    alt=""
                    loading="lazy"
                    className="mx-auto size-8 rounded-md object-cover mix-blend-multiply dark:mix-blend-screen dark:hue-rotate-180 dark:invert"
                  />
                ) : (
                  <span
                    aria-hidden="true"
                    className="mx-auto block size-8 rounded border border-dashed border-border/50 bg-muted/20"
                  />
                )}
              </td>
              <td className="min-w-0 py-2 pr-2 pl-2">
                <div className="flex min-w-0 items-center gap-1.5">
                  <span
                    className={cn(
                      'truncate text-[13px] font-medium',
                      hasModel ? 'text-foreground' : 'text-muted-foreground',
                    )}
                    title={
                      hasModel
                        ? [component.modelName, component.title].filter(Boolean).join(' · ')
                        : undefined
                    }
                  >
                    {hasModel ? component.modelName : t('chat.build.emptyModel')}
                  </span>
                  {mock ? (
                    <Badge className="shrink-0 border border-warning/40 bg-warning/10 px-1 text-[9px] leading-tight text-warning">
                      {t('chat.build.demoTag')}
                    </Badge>
                  ) : null}
                </div>
              </td>
              <td className="min-w-0 py-2 pl-2">
                <p
                  className="truncate text-[12.5px] text-muted-foreground"
                  title={modelDetail ?? undefined}
                >
                  {modelDetail || '—'}
                </p>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
