import {
  type ComponentRenderProps,
  defineComponent,
  type SubComponentOf,
} from '@openuidev/react-lang'
import { IconButton as OpenUiIconButton } from '@openuidev/react-ui/IconButton'
import {
  ScrollableTable as OpenUiTable,
  TableBody as OpenUiTableBody,
  TableCell as OpenUiTableCell,
  TableHead as OpenUiTableHead,
  TableHeader as OpenUiTableHeader,
  TableRow as OpenUiTableRow,
} from '@openuidev/react-ui/Table'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { z } from 'zod'

import { isSafeOpenUrl } from '../actions'

/** 单页行数上限：模型生成的大表在容器内翻页，避免一次撑高整条消息 */
const DEFAULT_PAGE_SIZE = 10

/** 单元格只承载基础类型；图片列用 URL 字符串，由渲染层决定是否画成缩略图 */
const cellSchema = z.union([z.string(), z.number(), z.boolean()])

type CellValue = z.infer<typeof cellSchema>

/** 表格列：只声明数据，渲染由父级 Table 统一完成 */
export const Col = defineComponent({
  name: 'Col',
  description:
    '表格列：label 是表头，data 是该列自上而下的单元格值；type=image 时单元格按图片 URL 渲染',
  props: z.object({
    label: z.string().describe('表头文案'),
    data: z.array(cellSchema).describe('该列单元格值，按行顺序排列'),
    type: z
      .enum(['text', 'image'])
      .optional()
      .describe('列类型，默认 text；image 表示单元格是 http/https 图片地址'),
  }),
  component: () => null,
})

type ColumnDef = {
  label: string
  data: CellValue[]
  type?: 'text' | 'image'
}

type TableRenderProps = ComponentRenderProps<{ columns: SubComponentOf<ColumnDef>[] }>

function TableCellValue({ column, value }: { column: ColumnDef; value: CellValue }) {
  // 外链图片可能 404/防盗链，失败后直接落到占位，避免表格出现破图
  const [failed, setFailed] = useState(false)
  if (column.type !== 'image') {
    return <>{String(value ?? '')}</>
  }

  // 图片地址沿用与链接相同的协议白名单；空值或非法地址渲染占位，不发起请求
  const src = typeof value === 'string' ? value.trim() : ''
  if (!src || !isSafeOpenUrl(src) || failed) {
    return <span className="text-muted-foreground">—</span>
  }

  return (
    <img
      src={src}
      alt=""
      loading="lazy"
      className="size-12 rounded-md border border-border bg-muted object-cover"
      onError={() => setFailed(true)}
    />
  )
}

function TableRenderer({ props }: TableRenderProps) {
  const [page, setPage] = useState(0)
  const columns = props.columns ?? []
  if (columns.length === 0) return null

  const columnDefs = columns.map((column) => column.props)
  // 所有行都没有可用图片时不渲染该列：整列「—」既占空间又像是缺数据
  const visibleColumns = columnDefs.filter(
    (column) =>
      column.type !== 'image' ||
      column.data.some(
        (value) => typeof value === 'string' && value.trim() !== '' && isSafeOpenUrl(value.trim())
      )
  )
  const rowCount = Math.max(0, ...visibleColumns.map((column) => column.data.length))
  const pageCount = Math.max(1, Math.ceil(rowCount / DEFAULT_PAGE_SIZE))
  const currentPage = Math.min(page, pageCount - 1)
  const startRow = currentPage * DEFAULT_PAGE_SIZE
  const visibleRowCount = Math.max(0, Math.min(DEFAULT_PAGE_SIZE, rowCount - startRow))

  if (visibleColumns.length === 0) return null

  return (
    <div className="flex flex-col gap-2">
      <OpenUiTable>
        <OpenUiTableHeader>
          <OpenUiTableRow>
            {visibleColumns.map((column) => (
              <OpenUiTableHead key={column.label}>{column.label}</OpenUiTableHead>
            ))}
          </OpenUiTableRow>
        </OpenUiTableHeader>
        <OpenUiTableBody>
          {Array.from({ length: visibleRowCount }, (_, rowOffset) => {
            const rowIndex = startRow + rowOffset
            return (
              <OpenUiTableRow key={rowIndex}>
                {visibleColumns.map((column) => (
                  <OpenUiTableCell key={column.label}>
                    <TableCellValue column={column} value={column.data[rowIndex] ?? ''} />
                  </OpenUiTableCell>
                ))}
              </OpenUiTableRow>
            )
          })}
        </OpenUiTableBody>
      </OpenUiTable>
      {pageCount > 1 ? (
        <div className="flex items-center justify-end gap-2">
          <OpenUiIconButton
            aria-label="上一页"
            size="small"
            variant="secondary"
            icon={<ChevronLeft size={16} />}
            disabled={currentPage === 0}
            onClick={() => setPage(currentPage - 1)}
          />
          <span className="tabular text-xs text-muted-foreground">
            {currentPage + 1} / {pageCount}
          </span>
          <OpenUiIconButton
            aria-label="下一页"
            size="small"
            variant="secondary"
            icon={<ChevronRight size={16} />}
            disabled={currentPage >= pageCount - 1}
            onClick={() => setPage(currentPage + 1)}
          />
        </div>
      ) : null}
    </div>
  )
}

/** 数据表格：官方 ScrollableTable 负责横向滚动，本项目只维护 Lang 契约与前端翻页 */
export const Table = defineComponent({
  name: 'Table',
  description: '数据表格：按列组织，每列自带数据数组；超过 10 行自动分页',
  props: z.object({
    columns: z.array(Col.ref).describe('列定义列表，至少一列'),
  }),
  component: TableRenderer,
})
