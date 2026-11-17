import { useTranslation } from 'react-i18next'
import { LoaderCircle } from 'lucide-react'

export interface CaseLoadingProps {
  /** 模型下载进度 0~100；null 表示无法获知进度，只展示扫动文案 */
  readonly progress: number | null
}

/** 模型加载遮罩：GLB 加载完成前占位，避免 3D 区先出现一块空白 */
export function CaseLoading({ progress }: CaseLoadingProps) {
  const { t } = useTranslation()
  const label = t('chat.casePanel.loading')

  return (
    <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-background/70 px-6 backdrop-blur-[1px]">
      <LoaderCircle className="size-5 animate-spin text-ring" aria-hidden="true" />
      <p role="status" className="text-center text-xs text-muted-foreground">
        {progress === null ? label : `${label} ${progress}%`}
      </p>
      {progress === null ? null : (
        <div className="h-1 w-36 overflow-hidden rounded-full bg-muted" aria-hidden="true">
          <div
            className="h-full rounded-full bg-ring transition-[width] duration-200"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}
    </div>
  )
}
