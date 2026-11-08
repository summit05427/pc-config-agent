import { useState } from 'react'
import {
  COST_STATUSES,
  COST_STATUS_LABELS,
  CREDENTIAL_SOURCES,
  CREDENTIAL_SOURCE_LABELS,
  USAGE_ORDERS,
  USAGE_ORDER_LABELS,
  USAGE_RESULTS,
  USAGE_RESULT_LABELS,
  type CostStatus,
  type CredentialSource,
  type UsageOrder,
  type UsageResult,
} from '../types'
import type { AdminProviderSummary } from '@/features/models/types'
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

/** 过滤条提交的增量；页码由页面统一重置为第一页。 */
export interface UsageFilterPatch {
  userId?: string
  provider?: string
  modelKey?: string
  credentialSource?: CredentialSource | ''
  costStatus?: CostStatus | ''
  status?: UsageResult | ''
  from?: string
  to?: string
  order?: UsageOrder
}

interface UsageFiltersProps {
  userId: string
  provider: string
  modelKey: string
  credentialSource: CredentialSource | ''
  costStatus: CostStatus | ''
  status: UsageResult | ''
  from: string
  to: string
  order: UsageOrder
  size: number
  providers: AdminProviderSummary[]
  onChange: (patch: UsageFilterPatch) => void
  onSizeChange: (size: number) => void
}

/** 文本过滤在回车或失焦时提交，避免每次按键触发请求。 */
export function UsageFilters({
  userId,
  provider,
  modelKey,
  credentialSource,
  costStatus,
  status,
  from,
  to,
  order,
  size,
  providers,
  onChange,
  onSizeChange,
}: UsageFiltersProps) {
  const [userIdInput, setUserIdInput] = useState(userId)
  const [modelKeyInput, setModelKeyInput] = useState(modelKey)

  return (
    <div className='flex flex-wrap items-end gap-3'>
      <div className='grid gap-1.5'>
        <Label htmlFor='usage-user-id'>用户 ID</Label>
        <Input
          id='usage-user-id'
          value={userIdInput}
          placeholder='用户公开 ID，回车查询'
          className='w-64'
          maxLength={36}
          onChange={(event) => setUserIdInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              onChange({ userId: userIdInput.trim() })
            }
          }}
          onBlur={() => onChange({ userId: userIdInput.trim() })}
        />
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='usage-provider'>Provider</Label>
        <Select
          value={provider || 'ALL'}
          onValueChange={(value) =>
            onChange({ provider: value === 'ALL' ? '' : value })
          }
        >
          <SelectTrigger id='usage-provider' className='w-40'>
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
        <Label htmlFor='usage-model'>模型标识</Label>
        <Input
          id='usage-model'
          value={modelKeyInput}
          placeholder='精确匹配，回车查询'
          className='w-56'
          maxLength={64}
          onChange={(event) => setModelKeyInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              onChange({ modelKey: modelKeyInput.trim() })
            }
          }}
          onBlur={() => onChange({ modelKey: modelKeyInput.trim() })}
        />
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='usage-source'>凭证来源</Label>
        <Select
          value={credentialSource || 'ALL'}
          onValueChange={(value) =>
            onChange({
              credentialSource: value === 'ALL' ? '' : (value as CredentialSource),
            })
          }
        >
          <SelectTrigger id='usage-source' className='w-32'>
            <SelectValue placeholder='全部来源' />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='ALL'>全部来源</SelectItem>
            {CREDENTIAL_SOURCES.map((item) => (
              <SelectItem key={item} value={item}>
                {CREDENTIAL_SOURCE_LABELS[item]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='usage-cost-status'>成本状态</Label>
        <Select
          value={costStatus || 'ALL'}
          onValueChange={(value) =>
            onChange({
              costStatus: value === 'ALL' ? '' : (value as CostStatus),
            })
          }
        >
          <SelectTrigger id='usage-cost-status' className='w-36'>
            <SelectValue placeholder='全部状态' />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='ALL'>全部状态</SelectItem>
            {COST_STATUSES.map((item) => (
              <SelectItem key={item} value={item}>
                {COST_STATUS_LABELS[item]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='usage-result'>调用结果</Label>
        <Select
          value={status || 'ALL'}
          onValueChange={(value) =>
            onChange({ status: value === 'ALL' ? '' : (value as UsageResult) })
          }
        >
          <SelectTrigger id='usage-result' className='w-32'>
            <SelectValue placeholder='全部结果' />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='ALL'>全部结果</SelectItem>
            {USAGE_RESULTS.map((item) => (
              <SelectItem key={item} value={item}>
                {USAGE_RESULT_LABELS[item]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='usage-from'>起始日期</Label>
        <Input
          id='usage-from'
          type='date'
          value={from}
          className='w-40'
          onChange={(event) => onChange({ from: event.target.value })}
        />
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='usage-to'>截止日期</Label>
        <Input
          id='usage-to'
          type='date'
          value={to}
          className='w-40'
          onChange={(event) => onChange({ to: event.target.value })}
        />
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='usage-order'>排序</Label>
        <Select
          value={order}
          onValueChange={(value) => onChange({ order: value as UsageOrder })}
        >
          <SelectTrigger id='usage-order' className='w-32'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {USAGE_ORDERS.map((item) => (
              <SelectItem key={item} value={item}>
                {USAGE_ORDER_LABELS[item]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='usage-page-size'>每页条数</Label>
        <Select
          value={String(size)}
          onValueChange={(value) => onSizeChange(Number(value))}
        >
          <SelectTrigger id='usage-page-size' className='w-28'>
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
