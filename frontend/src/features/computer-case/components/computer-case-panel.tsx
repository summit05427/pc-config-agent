import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { PanelRightClose } from 'lucide-react'

import { Button } from '@/shared/ui/button'

import { useComputerCase } from '../hooks/use-computer-case'
import { CaseLoading } from './case-loading'
import { CaseNavigation } from './case-navigation'

export interface ComputerCasePanelProps {
  /** 点击隐藏：由页面卸载本面板，对话区回到水平居中 */
  readonly onHide: () => void
}

/**
 * 机箱 3D 预览面板。
 *
 * 宽度由页面布局决定（flex 自适应），这里只负责导航、画布与加载/错误态；
 * 组件卸载即释放 WebGL 上下文，隐藏后不会继续占用 GPU。
 */
export function ComputerCasePanel({ onHide }: ComputerCasePanelProps) {
  const { t } = useTranslation()
  const canvasContainerRef = useRef<HTMLDivElement | null>(null)
  const computerCase = useComputerCase(canvasContainerRef)

  return (
    <aside
      className="flex w-[clamp(340px,28%,480px)] min-h-0 shrink-0 flex-col border-l border-border bg-canvas"
      aria-label={t('chat.casePanel.label')}
    >
      <div className="flex shrink-0 items-center justify-end px-2 pt-2">
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={t('chat.casePanel.hide')}
          title={t('chat.casePanel.hide')}
          onClick={onHide}
        >
          <PanelRightClose className="size-4" />
        </Button>
      </div>

      {/* 导航整体下移：与隐藏按钮之间留出呼吸空间，避免贴住面板顶部 */}
      {computerCase.navItems.length > 0 ? (
        <div className="shrink-0 px-3 pt-3 pb-1">
          <CaseNavigation
            items={computerCase.navItems}
            activeId={computerCase.activeId}
            onSelect={computerCase.select}
          />
        </div>
      ) : null}

      <div className="relative min-h-0 flex-1">
        {/* renderer 的 canvas 由场景工厂挂到这个节点 */}
        <div ref={canvasContainerRef} className="h-full w-full" />

        {computerCase.isLoading ? <CaseLoading progress={computerCase.progress} /> : null}

        {computerCase.hasError ? (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 px-6 text-center">
            <p className="text-sm text-muted-foreground">{t('chat.casePanel.loadFailed')}</p>
            <Button variant="outline" size="sm" onClick={computerCase.retry}>
              {t('chat.casePanel.retry')}
            </Button>
          </div>
        ) : null}
      </div>
    </aside>
  )
}
