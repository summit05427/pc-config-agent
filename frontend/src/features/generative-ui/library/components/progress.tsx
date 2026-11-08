import { type ComponentRenderProps, defineComponent } from '@openuidev/react-lang'
import { z } from 'zod'

type ProgressProps = { value: number; label?: string }

function ProgressRenderer({ props }: ComponentRenderProps<ProgressProps>) {
  const value = Math.min(100, Math.max(0, props.value))

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        {props.label ? <span>{props.label}</span> : <span />}
        <span className="tabular">{value}%</span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={props.label}
        className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
      >
        <div
          className="h-full rounded-full bg-primary transition-[width] duration-300"
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  )
}

/**
 * 进度条：官方组件库没有对应原语，这里用 Design Token 自研。
 * 只做展示，不接受动作，避免和真实任务进度语义混淆。
 */
export const Progress = defineComponent({
  name: 'Progress',
  description: '进度条：展示 0 到 100 的完成度',
  props: z.object({
    value: z.number().min(0).max(100).describe('完成度，0 到 100'),
    label: z.string().optional().describe('进度条上方的说明文案'),
  }),
  component: ProgressRenderer,
})
