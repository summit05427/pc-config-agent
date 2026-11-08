import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface PaginationBarProps {
  page: number
  size: number
  total: number
  isDisabled?: boolean
  onPageChange: (page: number) => void
}

/**
 * 服务端分页条。
 *
 * 页码与总量全部来自后端 `{list,total,page,size}`，前端只负责切换页码，
 * 不在本地切片，避免与数据库排序结果不一致。
 */
export function PaginationBar({
  page,
  size,
  total,
  isDisabled,
  onPageChange,
}: PaginationBarProps) {
  const totalPages = Math.max(1, Math.ceil(total / size))
  const isFirstPage = page <= 1
  const isLastPage = page >= totalPages

  return (
    <div className='flex flex-col items-center justify-between gap-3 sm:flex-row'>
      <p className='text-sm text-muted-foreground'>
        共 {total} 条，第 {page} / {totalPages} 页
      </p>
      <div className='flex items-center gap-2'>
        <Button
          variant='outline'
          size='sm'
          disabled={isDisabled || isFirstPage}
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronLeft />
          上一页
        </Button>
        <Button
          variant='outline'
          size='sm'
          disabled={isDisabled || isLastPage}
          onClick={() => onPageChange(page + 1)}
        >
          下一页
          <ChevronRight />
        </Button>
      </div>
    </div>
  )
}
