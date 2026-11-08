import type { ModelPricingVersion } from '../types'
import { formatDateTime } from '@/lib/format'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

interface PricingVersionsTableProps {
  versions: ModelPricingVersion[]
  isPending: boolean
  hasError: boolean
}

/** 单价按「每百万 token」展示，保留 6 位小数以内，避免把 0.15 显示成 0.150000。 */
function formatPrice(value: number): string {
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 6 })
}

export function PricingVersionsTable({
  versions,
  isPending,
  hasError,
}: PricingVersionsTableProps) {
  if (isPending) {
    return (
      <p className='text-muted-foreground py-6 text-center text-sm'>加载中…</p>
    )
  }

  if (hasError) {
    return (
      <p className='text-destructive py-6 text-center text-sm'>
        定价版本加载失败，请稍后重试。
      </p>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>生效时间</TableHead>
          <TableHead>币种</TableHead>
          <TableHead className='text-end'>输入 / 百万 token</TableHead>
          <TableHead className='text-end'>输出 / 百万 token</TableHead>
          <TableHead>创建时间</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {versions.map((version) => (
          <TableRow key={version.id}>
            <TableCell>{formatDateTime(version.effectiveFrom)}</TableCell>
            <TableCell>{version.currency}</TableCell>
            <TableCell className='text-end'>
              {formatPrice(version.inputPricePerMillion)}
            </TableCell>
            <TableCell className='text-end'>
              {formatPrice(version.outputPricePerMillion)}
            </TableCell>
            <TableCell>{formatDateTime(version.createdAt)}</TableCell>
          </TableRow>
        ))}
        {versions.length === 0 && (
          <TableRow>
            <TableCell
              colSpan={5}
              className='text-muted-foreground py-6 text-center'
            >
              尚未配置定价，成本统计将记为未知
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  )
}
