import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { AdminProviderSummary } from '../types'

interface ProvidersBarProps {
  providers: AdminProviderSummary[]
  isPending: boolean
  hasError: boolean
  onToggle: (provider: AdminProviderSummary) => void
}

/** Provider 目录条：停用会使其下全部模型对新调用不可用，因此由父级二次确认。 */
export function ProvidersBar({
  providers,
  isPending,
  hasError,
  onToggle,
}: ProvidersBarProps) {
  if (isPending) {
    return <p className='text-sm text-muted-foreground'>Provider 目录加载中…</p>
  }

  if (hasError) {
    return (
      <p className='text-sm text-destructive'>
        Provider 目录加载失败，模型筛选暂不可用。
      </p>
    )
  }

  return (
    <div className='flex flex-wrap items-center gap-2'>
      {providers.map((provider) => (
        <div
          key={provider.code}
          className='flex items-center gap-2 rounded-md border px-3 py-1.5'
        >
          <span className='text-sm font-medium'>{provider.displayName}</span>
          <span className='text-xs text-muted-foreground'>
            {provider.enabledModelCount}/{provider.modelCount} 已启用
          </span>
          <Badge variant={provider.enabled ? 'secondary' : 'outline'}>
            {provider.enabled ? '启用中' : '已停用'}
          </Badge>
          <Button
            variant='outline'
            size='sm'
            onClick={() => onToggle(provider)}
          >
            {provider.enabled ? '停用' : '启用'}
          </Button>
        </div>
      ))}
      {providers.length === 0 && (
        <p className='text-sm text-muted-foreground'>暂无 Provider</p>
      )}
    </div>
  )
}
