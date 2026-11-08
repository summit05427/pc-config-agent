import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import {
  createModelPricing,
  modelPricingQueryOptions,
} from '../api/admin-models-api'
import { PricingVersionsTable } from './pricing-versions-table'
import type { AdminModelSummary } from '../types'
import { getHttpErrorMessage } from '@/core/http/errors'
import { queryKeys } from '@/lib/query-keys'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const pricingFormSchema = z.object({
  currency: z.string().regex(/^[A-Za-z]{3}$/, '币种必须是 3 位字母，例如 USD'),
  inputPricePerMillion: z.number().min(0, '输入单价不能为负数'),
  outputPricePerMillion: z.number().min(0, '输出单价不能为负数'),
  effectiveFrom: z.string().min(1, '请选择生效时间'),
})

type PricingFormValues = z.infer<typeof pricingFormSchema>

/** datetime-local 需要本地时间且不含秒；直接 toISOString 会带 UTC 偏移导致显示错位。 */
function toLocalInputValue(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return [
    date.getFullYear(),
    '-',
    pad(date.getMonth() + 1),
    '-',
    pad(date.getDate()),
    'T',
    pad(date.getHours()),
    ':',
    pad(date.getMinutes()),
  ].join('')
}

interface ModelPricingDialogProps {
  model: AdminModelSummary
  onOpenChange: (open: boolean) => void
}

/**
 * 定价维护：上半部分展示版本历史，下半部分追加新版本。
 *
 * 已生效的历史版本不可编辑，只能新增后续版本，保证用量台账的历史成本可复现。
 */
export function ModelPricingDialog({
  model,
  onOpenChange,
}: ModelPricingDialogProps) {
  const queryClient = useQueryClient()
  const pricingQuery = useQuery(
    modelPricingQueryOptions(model.provider, model.modelKey, {
      page: 1,
      size: 20,
    })
  )

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<PricingFormValues>({
    resolver: zodResolver(pricingFormSchema),
    defaultValues: {
      currency: 'USD',
      inputPricePerMillion: 0,
      outputPricePerMillion: 0,
      effectiveFrom: toLocalInputValue(new Date()),
    },
  })

  const createMutation = useMutation({
    mutationFn: (values: PricingFormValues) =>
      createModelPricing(model.provider, model.modelKey, {
        currency: values.currency.toUpperCase(),
        inputPricePerMillion: Number(values.inputPricePerMillion),
        outputPricePerMillion: Number(values.outputPricePerMillion),
        effectiveFrom: new Date(values.effectiveFrom).toISOString(),
      }),
    onSuccess: () => {
      toast.success('定价版本已新增，对新调用立即生效')
      reset()
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminModels.all })
    },
    onError: (error) => toast.error(getHttpErrorMessage(error)),
  })

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>定价维护</DialogTitle>
          <DialogDescription>
            {model.provider}:{model.modelKey} 的单价按每百万 token
            配置，只追加版本，历史用量金额不重算。
          </DialogDescription>
        </DialogHeader>

        <div className='flex max-h-64 flex-col gap-2 overflow-y-auto'>
          <p className='text-sm font-medium'>版本历史</p>
          <PricingVersionsTable
            versions={pricingQuery.data?.list ?? []}
            isPending={pricingQuery.isPending}
            hasError={pricingQuery.isError}
          />
        </div>

        <form
          className='grid gap-3 border-t pt-4'
          onSubmit={handleSubmit((values) => createMutation.mutate(values))}
        >
          <p className='text-sm font-medium'>新增版本</p>
          <div className='grid grid-cols-2 gap-3'>
            <div className='grid gap-1.5'>
              <Label htmlFor='pricing-currency'>币种</Label>
              <Input id='pricing-currency' {...register('currency')} />
              {errors.currency && (
                <p className='text-destructive text-xs'>
                  {errors.currency.message}
                </p>
              )}
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='pricing-effective-from'>生效时间</Label>
              <Input
                id='pricing-effective-from'
                type='datetime-local'
                {...register('effectiveFrom')}
              />
              {errors.effectiveFrom && (
                <p className='text-destructive text-xs'>
                  {errors.effectiveFrom.message}
                </p>
              )}
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='pricing-input'>输入单价 / 百万 token</Label>
              <Input
                id='pricing-input'
                type='number'
                step='0.000001'
                min={0}
                {...register('inputPricePerMillion', { valueAsNumber: true })}
              />
              {errors.inputPricePerMillion && (
                <p className='text-destructive text-xs'>
                  {errors.inputPricePerMillion.message}
                </p>
              )}
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='pricing-output'>输出单价 / 百万 token</Label>
              <Input
                id='pricing-output'
                type='number'
                step='0.000001'
                min={0}
                {...register('outputPricePerMillion', { valueAsNumber: true })}
              />
              {errors.outputPricePerMillion && (
                <p className='text-destructive text-xs'>
                  {errors.outputPricePerMillion.message}
                </p>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button
              type='button'
              variant='outline'
              onClick={() => onOpenChange(false)}
            >
              关闭
            </Button>
            <Button type='submit' disabled={createMutation.isPending}>
              {createMutation.isPending ? '保存中…' : '新增版本'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
