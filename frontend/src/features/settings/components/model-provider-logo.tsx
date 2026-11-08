import { cn } from '@/shared/lib/utils'

import { getProviderMeta } from '../model/provider-meta'

export type ProviderLogoSize = 'sm' | 'md'

const SIZE_CLASSES: Record<ProviderLogoSize, string> = {
  sm: 'size-8 rounded-[var(--cds-radius-btn-xs)]',
  md: 'size-10 rounded-[var(--cds-radius-btn-md)]',
}

const SIZE_PIXELS: Record<ProviderLogoSize, number> = {
  sm: 32,
  md: 40,
}

export interface ModelProviderLogoProps {
  providerCode: string
  /** 服务端展示名或本地品牌名，用于图片加载失败时的替代文本与首字母回退 */
  label: string
  size?: ProviderLogoSize
}

/** 厂商标识：命中本地 logo 渲染图片，未知厂商回退为首字母，保持列表对齐 */
export function ModelProviderLogo({ providerCode, label, size = 'sm' }: ModelProviderLogoProps) {
  const { logoSrc, name } = getProviderMeta(providerCode, label)
  const pixels = SIZE_PIXELS[size]

  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center justify-center overflow-hidden border border-border bg-surface-raised',
        SIZE_CLASSES[size],
      )}
    >
      {logoSrc ? (
        <img
          src={logoSrc}
          alt=""
          aria-hidden="true"
          width={pixels}
          height={pixels}
          loading="lazy"
          className="size-full object-contain p-1.5"
        />
      ) : (
        <span aria-hidden="true" className="text-xs font-semibold text-muted-foreground">
          {name.slice(0, 1).toUpperCase()}
        </span>
      )}
    </span>
  )
}
