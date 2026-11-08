import { cn } from '@/shared/lib/utils'

/** 预览画面只表达「明 / 暗」两种静态外观，system 由两者拼接而成 */
export type ThemePreviewTone = 'light' | 'dark'
export type ThemePreviewVariant = ThemePreviewTone | 'system'

export interface ThemePreviewArtProps {
  /** light / dark 绘制单一面板，system 左右各半以表达跟随系统 */
  variant: ThemePreviewVariant
  className?: string
}

interface PreviewPalette {
  canvas: string
  sidebar: string
  chrome: string
  contentStrong: string
  contentSoft: string
}

/*
 * 使用固定灰度阶而非当前主题的语义色，保证深色卡片在浅色界面下
 * 仍然预览为深色，不被 `.dark` 的变量覆盖。
 */
const PREVIEW_PALETTES: Record<ThemePreviewTone, PreviewPalette> = {
  light: {
    canvas: 'bg-[var(--cds-gray-20)]',
    sidebar: 'bg-[var(--cds-gray-70)]',
    chrome: 'border-[var(--cds-gray-150)]',
    contentStrong: 'bg-[var(--cds-gray-250)]',
    contentSoft: 'bg-[var(--cds-gray-150)]',
  },
  dark: {
    canvas: 'bg-[var(--cds-gray-850)]',
    sidebar: 'bg-[var(--cds-gray-800)]',
    chrome: 'border-white/10',
    contentStrong: 'bg-[var(--cds-gray-550)]',
    contentSoft: 'bg-[var(--cds-gray-700)]',
  },
}

/** 一张微缩界面：侧栏 + 顶部工具条 + 内容行 + 底部输入区，避免外部图片依赖 */
function PreviewWindow({ tone }: { tone: ThemePreviewTone }) {
  const palette = PREVIEW_PALETTES[tone]

  return (
    <div className={cn('absolute inset-0', palette.canvas)}>
      <span className={cn('absolute inset-y-0 left-0 w-1/5', palette.sidebar)} />
      <span className={cn('absolute inset-x-0 top-0 h-3 border-b', palette.chrome)} />
      <span className="absolute left-3 top-2.5 h-1.5 w-1/3 rounded-full bg-clay/70" />
      <span
        className={cn('absolute left-1/4 right-3 top-7 h-1.5 rounded-full', palette.contentStrong)}
      />
      <span
        className={cn('absolute left-1/4 right-8 top-10 h-1 rounded-full', palette.contentSoft)}
      />
      <span
        className={cn('absolute left-1/4 right-6 top-12 h-1 rounded-full', palette.contentSoft)}
      />
      <span
        className={cn('absolute bottom-2.5 left-3 right-3 h-4 rounded-sm', palette.contentSoft)}
      />
      <span className="absolute bottom-3 left-2 size-2 rounded-full bg-clay/80" />
    </div>
  )
}

/**
 * 主题预览画面。
 *
 * 画面全部由 Token 绘制，不引入图片资源；父级只需要提供宽高与溢出裁剪。
 * system 变体把浅色、深色两块并排，中间一条发丝线表达「跟随系统」。
 */
export function ThemePreviewArt({ variant, className }: ThemePreviewArtProps) {
  const tones: readonly ThemePreviewTone[] = variant === 'system' ? ['light', 'dark'] : [variant]
  const isSplit = tones.length > 1

  return (
    <div className={cn('absolute inset-0 flex', className)} aria-hidden="true">
      {tones.map((tone) => (
        <div key={tone} className={cn('relative overflow-hidden', isSplit ? 'w-1/2' : 'w-full')}>
          <PreviewWindow tone={tone} />
        </div>
      ))}
      {isSplit ? (
        <span className="absolute inset-y-0 left-1/2 w-px bg-[var(--cds-gray-450)]/60" />
      ) : null}
    </div>
  )
}
