import { useState } from 'react'
import { Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  FEEDBACK_REASONS,
  FEEDBACK_RATINGS,
  RATING_LABELS,
  REASON_LABELS,
  type FeedbackRating,
  type FeedbackReason,
} from '../types'

/** 过滤条提交的增量；页码由页面统一重置为第一页。 */
export interface FeedbackFilterPatch {
  rating?: FeedbackRating | ''
  reasonCode?: FeedbackReason | ''
  threadId?: string
  from?: string
  to?: string
}

interface FeedbackFiltersProps {
  rating: FeedbackRating | ''
  reasonCode: FeedbackReason | ''
  threadId: string
  from: string
  to: string
  isExporting: boolean
  onChange: (patch: FeedbackFilterPatch) => void
  onExport: () => void
}

/** 文本过滤在回车或失焦时提交，避免每次按键触发请求。 */
export function FeedbackFilters({
  rating,
  reasonCode,
  threadId,
  from,
  to,
  isExporting,
  onChange,
  onExport,
}: FeedbackFiltersProps) {
  const [threadIdInput, setThreadIdInput] = useState(threadId)

  const submitThreadId = (): void => onChange({ threadId: threadIdInput.trim() })

  return (
    <div className='flex flex-wrap items-end gap-3'>
      <div className='grid gap-1.5'>
        <Label htmlFor='feedback-rating'>评分</Label>
        <Select
          value={rating || 'ALL'}
          onValueChange={(value) =>
            onChange({ rating: value === 'ALL' ? '' : (value as FeedbackRating) })
          }
        >
          <SelectTrigger id='feedback-rating' className='w-28'>
            <SelectValue placeholder='全部评分' />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='ALL'>全部评分</SelectItem>
            {FEEDBACK_RATINGS.map((item) => (
              <SelectItem key={item} value={item}>
                {RATING_LABELS[item]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className='grid gap-1.5'>
        <Label htmlFor='feedback-reason'>原因</Label>
        <Select
          value={reasonCode || 'ALL'}
          onValueChange={(value) =>
            onChange({
              reasonCode: value === 'ALL' ? '' : (value as FeedbackReason),
            })
          }
        >
          <SelectTrigger id='feedback-reason' className='w-36'>
            <SelectValue placeholder='全部原因' />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='ALL'>全部原因</SelectItem>
            {FEEDBACK_REASONS.map((item) => (
              <SelectItem key={item} value={item}>
                {REASON_LABELS[item]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className='grid gap-1.5'>
        <Label htmlFor='feedback-thread'>会话 ID</Label>
        <Input
          id='feedback-thread'
          value={threadIdInput}
          placeholder='精确匹配，回车查询'
          className='w-64'
          maxLength={64}
          onChange={(event) => setThreadIdInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              submitThreadId()
            }
          }}
          onBlur={submitThreadId}
        />
      </div>

      <div className='grid gap-1.5'>
        <Label htmlFor='feedback-from'>起始日期</Label>
        <Input
          id='feedback-from'
          type='date'
          value={from}
          className='w-40'
          onChange={(event) => onChange({ from: event.target.value })}
        />
      </div>

      <div className='grid gap-1.5'>
        <Label htmlFor='feedback-to'>截止日期</Label>
        <Input
          id='feedback-to'
          type='date'
          value={to}
          className='w-40'
          onChange={(event) => onChange({ to: event.target.value })}
        />
      </div>

      <Button
        variant='outline'
        size='sm'
        disabled={isExporting}
        onClick={onExport}
      >
        <Download className='size-4' />
        {isExporting ? '导出中…' : '导出 CSV'}
      </Button>
    </div>
  )
}
