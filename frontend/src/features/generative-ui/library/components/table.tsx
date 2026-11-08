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

/** 单页行数上限：模型生成的大表在容器内翻页，避免一次撑高整条消息 */
const DEFAULT_PAGE_SIZE = 10

const cellSchema = z.union([z.string(), z.number(), z.boolean()])

/** 表格列：只声明数据，渲染由父级 Table 统一完成 */
export const Col = defineComponent({
  name: 'Col',
  description: '表格列：label 是表头，data 是该列自上而下的单元格值',
  props: z.object({
    label: z.string().describe('表头文案'),
    data: z.array(cellSchema).describe('该列单元格值，按行顺序排列'),
  }),
  component: () => null,
})

type ColumnDef = { label: string; data: (string | number | boolean)[] }

type TableRenderProps = ComponentRenderProps<{ columns: SubComponentOf<ColumnDef>[] }>

function TableRenderer({ props }: TableRenderProps) {
  const [page, setPage] = useState(0)
  const columns = props.columns ?? []
  if (columns.length === 0) return null

  const columnDefs = columns.map((column) => column.props)
  const rowCount = Math.max(0, ...columnDefs.map((column) => column.data.length))
  const pageCount = Math.max(1, Math.ceil(rowCount / DEFAULT_PAGE_SIZE))
  const currentPage = Math.min(page, pageCount - 1)
  const startRow = currentPage * DEFAULT_PAGE_SIZE
  const visibleRowCount = Math.max(0, Math.min(DEFAULT_PAGE_SIZE, rowCount - startRow))

  return (
    <div className="flex flex-col gap-2">
      <OpenUiTable>
        <OpenUiTableHeader>
          <OpenUiTableRow>
            {columnDefs.map((column) => (
              <OpenUiTableHead key={column.label}>{column.label}</OpenUiTableHead>
            ))}
          </OpenUiTableRow>
        </OpenUiTableHeader>
        <OpenUiTableBody>
          {Array.from({ length: visibleRowCount }, (_, rowOffset) => {
            const rowIndex = startRow + rowOffset
            return (
              <OpenUiTableRow key={rowIndex}>
                {columnDefs.map((column) => (
                  <OpenUiTableCell key={column.label}>
                    {String(column.data[rowIndex] ?? '')}
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
