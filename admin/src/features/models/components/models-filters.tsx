import { useState } from 'react'
import {
  MODEL_ENABLED_FILTERS,
  type AdminProviderSummary,
  type ModelEnabledFilter,
} from '../types'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const PAGE_SIZES = [10, 20, 50, 100]

const ENABLED_LABELS: Record<ModelEnabledFilter, string> = {
  '': '全部状态',
  true: '仅启用',
  false: '仅停用',
}

interface ModelsFiltersProps {
  keyword: string
  provider: string
  enabled: ModelEnabledFilter
  size: number
  providers: AdminProviderSummary[]
  onKeywordChange: (keyword: string) => void
  onProviderChange: (provider: string) => void
  onEnabledChange: (enabled: ModelEnabledFilter) => void
  onSizeChange: (size: number) => void
}

/** 过滤条只做输入收集，关键字在回车或失焦时提交，避免每次按键触发请求。 */
export function ModelsFilters({
  keyword,
  provider,
  enabled,
  size,
  providers,
  onKeywordChange,
  onProviderChange,
  onEnabledChange,
  onSizeChange,
}: ModelsFiltersProps) {
  const [keywordInput, setKeywordInput] = useState(keyword)

  return (
    <div className='flex flex-wrap items-end gap-3'>
      <div className='grid gap-1.5'>
        <Label htmlFor='model-keyword'>展示名或模型标识</Label>
        <Input
          id='model-keyword'
          value={keywordInput}
          placeholder='输入关键字后回车'
          className='w-64'
          onChange={(event) => setKeywordInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              onKeywordChange(keywordInput.trim())
            }
          }}
          onBlur={() => onKeywordChange(keywordInput.trim())}
        />
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='model-provider'>Provider</Label>
        <Select
          value={provider || 'ALL'}
          onValueChange={(value) =>
            onProviderChange(value === 'ALL' ? '' : value)
          }
        >
          <SelectTrigger id='model-provider' className='w-40'>
            <SelectValue placeholder='全部 Provider' />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='ALL'>全部 Provider</SelectItem>
            {providers.map((item) => (
              <SelectItem key={item.code} value={item.code}>
                {item.displayName}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='model-enabled'>启用状态</Label>
        <Select
          value={enabled || 'ALL'}
          onValueChange={(value) =>
            onEnabledChange(value === 'ALL' ? '' : (value as ModelEnabledFilter))
          }
        >
          <SelectTrigger id='model-enabled' className='w-32'>
            <SelectValue placeholder='全部状态' />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='ALL'>全部状态</SelectItem>
            {MODEL_ENABLED_FILTERS.filter((item) => item !== '').map((item) => (
              <SelectItem key={item} value={item}>
                {ENABLED_LABELS[item]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='model-page-size'>每页条数</Label>
        <Select
          value={String(size)}
          onValueChange={(value) => onSizeChange(Number(value))}
        >
          <SelectTrigger id='model-page-size' className='w-28'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PAGE_SIZES.map((item) => (
              <SelectItem key={item} value={String(item)}>
                {item}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  )
}
