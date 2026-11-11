import { useTranslation } from 'react-i18next'

import type { BuildResult } from '@/features/sessions/api'
import { formatFen } from '@/shared/lib/format'
import { Button } from '@/shared/ui/button'
import {
    Dialog,
    DialogClose,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/shared/ui/dialog'

import { BuildComponentRow } from './build-result-component-row'
import { BuildCompatibilityList } from './build-compatibility-list'

export interface BuildDetailDialogProps {
    readonly result: BuildResult
    readonly open: boolean
    readonly onOpenChange: (open: boolean) => void
}

/**
 * 配置完整详情弹窗。
 *
 * 直接复用 {@link BuildComponentRow}，保证卡片内摘要与详情视图使用同一份
 * 结构化数据和同一套「演示价 / 未核验」标注规则，避免两处渲染口径漂移。
 */
export function BuildDetailDialog({ result, open, onOpenChange }: BuildDetailDialogProps) {
    const { t } = useTranslation()
    // 理由只按 hardwareId 关联；匹配不到时该行不展示理由，与卡片保持一致
    const reasonByHardwareId = new Map(
        (result.componentReasons ?? []).map((item) => [item.hardwareId, item.reason]),
    )

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent
                className="sm:max-w-5xl"
                data-testid="build-detail-dialog"
            >
                <DialogHeader>
                    <DialogTitle>{t('chat.build.detailTitle')}</DialogTitle>
                    <DialogDescription>{t('chat.build.detailDescription')}</DialogDescription>
                </DialogHeader>

                <div className="max-h-[74vh] space-y-3 overflow-y-auto pr-1">
                    {/* 校验清单置顶：先看兼容性结论，再看逐件参数与跑分 */}
                    <div className="rounded-lg border border-border bg-muted/20 px-3 py-2">
                        <BuildCompatibilityList checks={result.compatibility} />
                    </div>

                    <div className="rounded-lg border border-border">
                        <ul className="divide-y divide-border">
                            {result.components.map((component) => (
                                <BuildComponentRow
                                    key={component.category}
                                    component={component}
                                    reason={
                                        component.hardwareId
                                            ? reasonByHardwareId.get(component.hardwareId)
                                            : undefined
                                    }
                                />
                            ))}
                        </ul>
                    </div>
                </div>

                <DialogFooter className="items-center justify-between gap-3 sm:justify-between">
                    <div>
                        <p className="text-xs text-muted-foreground">{t('chat.build.total')}</p>
                        <p className="text-lg font-semibold tabular-nums">
                            {formatFen(result.totalPriceFen)}
                        </p>
                    </div>
                    <DialogClose asChild>
                        <Button variant="outline" size="sm">
                            {t('chat.build.detailClose')}
                        </Button>
                    </DialogClose>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
