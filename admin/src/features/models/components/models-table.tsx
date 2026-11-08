import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { TableState } from '@/components/table-state'
import { CAPABILITY_SOURCE_LABELS, type AdminModelSummary } from '../types'

interface ModelsTableProps {
  models: AdminModelSummary[]
  isPending: boolean
  hasError: boolean
  isStatusUpdating: boolean
  onOpenPricing: (model: AdminModelSummary) => void
  onToggleStatus: (model: AdminModelSummary) => void
  onRetry: () => void
}

function statusLabel(model: AdminModelSummary): string {
  if (!model.providerEnabled) return 'Provider 已停用'
  return model.enabled ? '启用中' : '已停用'
}

function pricingLabel(model: AdminModelSummary): string {
  if (!model.latestPricing) return '未配置'
  return `${model.latestPricing.currency} 输入 ${model.latestPricing.inputPricePerMillion} / 输出 ${model.latestPricing.outputPricePerMillion}`
}

export function ModelsTable({
  models,
  isPending,
  hasError,
  isStatusUpdating,
  onOpenPricing,
  onToggleStatus,
  onRetry,
}: ModelsTableProps) {
  if (isPending) {
    return <TableState kind='loading' description='正在获取模型目录…' />
  }

  if (hasError) {
    return (
      <TableState
        kind='error'
        title='模型目录加载失败'
        description='请稍后重试，或点击下方按钮重新加载。'
        onRetry={onRetry}
      />
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Provider</TableHead>
          <TableHead>模型标识</TableHead>
          <TableHead>展示名</TableHead>
          <TableHead>能力</TableHead>
          <TableHead>上下文</TableHead>
          <TableHead>状态</TableHead>
          <TableHead>最近定价（每百万 token）</TableHead>
          <TableHead className='text-end'>操作</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {models.map((model) => (
          <TableRow key={`${model.provider}:${model.modelKey}`}>
            <TableCell className='font-medium'>{model.provider}</TableCell>
            <TableCell>{model.modelKey}</TableCell>
            <TableCell>{model.displayName}</TableCell>
            <TableCell>
              <div className='flex flex-wrap gap-1'>
                {model.capabilities.map((capability) => (
                  <Badge key={capability} variant='outline'>
                    {capability}
                  </Badge>
                ))}
                {model.capabilities.length === 0 && (
                  <span className='text-muted-foreground'>—</span>
                )}
              </div>
              <p className='mt-1 text-xs text-muted-foreground'>
                {CAPABILITY_SOURCE_LABELS[model.capabilitySource] ??
                  model.capabilitySource}
              </p>
            </TableCell>
            <TableCell>{model.contextWindow ?? '—'}</TableCell>
            <TableCell>
              <Badge
                variant={
                  model.enabled && model.providerEnabled
                    ? 'secondary'
                    : 'outline'
                }
              >
                {statusLabel(model)}
              </Badge>
            </TableCell>
            <TableCell className='text-xs'>{pricingLabel(model)}</TableCell>
            <TableCell className='text-end'>
              <div className='flex justify-end gap-2'>
                <Button
                  variant='outline'
                  size='sm'
                  onClick={() => onOpenPricing(model)}
                >
                  定价
                </Button>
                <Button
                  variant={model.enabled ? 'outline' : 'default'}
                  size='sm'
                  disabled={isStatusUpdating}
                  onClick={() => onToggleStatus(model)}
                >
                  {model.enabled ? '停用' : '启用'}
                </Button>
              </div>
            </TableCell>
          </TableRow>
        ))}
        {models.length === 0 && (
          <TableState
            kind='empty'
            colSpan={8}
            title='没有符合条件的模型'
            description='调整关键字、Provider 或启用状态后再试。'
          />
        )}
      </TableBody>
    </Table>
  )
}
