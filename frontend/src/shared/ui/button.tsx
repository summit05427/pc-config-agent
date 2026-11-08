import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { Slot } from 'radix-ui'

import { cn } from '@/shared/lib/utils'

/*
 * 与 Vue 基线保持一致：控件高度严格取 CDS 阶梯（xs 23 / sm 26 / md 32 / lg 40），
 * 圆角取 --cds-radius-btn-xs(6px) 与 --cds-radius-btn-md(8px)，不写任意值。
 */
const buttonVariants = cva(
  // justify-center 保证图标在方形按钮内水平居中；文本按钮需要左对齐时由调用方显式覆盖
  'group/button inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-[var(--cds-radius-btn-md)] border border-transparent bg-clip-padding text-sm font-medium outline-none select-none transition-[background-color,border-color,color,box-shadow] duration-150 focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/35 disabled:pointer-events-none disabled:opacity-45 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*=size-])]:size-4',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground hover:bg-primary/90',
        outline:
          'border-border bg-surface hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground',
        secondary:
          'bg-secondary text-secondary-foreground hover:bg-secondary/70 aria-expanded:bg-secondary aria-expanded:text-secondary-foreground',
        ghost:
          'hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground',
        destructive:
          'bg-destructive/10 text-destructive hover:bg-destructive/18 focus-visible:border-destructive/40 focus-visible:ring-destructive/30 dark:bg-destructive/20 dark:hover:bg-destructive/30 dark:focus-visible:ring-destructive/40',
        link: 'text-primary underline-offset-4 hover:underline',
      },
      size: {
        default:
          'h-[var(--control-height-md)] gap-1.5 px-3 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2',
        xs: 'h-[var(--control-height-xs)] gap-1 rounded-[var(--cds-radius-btn-xs)] px-1.5 text-xs has-data-[icon=inline-end]:pr-1 has-data-[icon=inline-start]:pl-1 [&_svg:not([class*=size-])]:size-3',
        sm: 'h-[var(--control-height-sm)] gap-1 rounded-[var(--cds-radius-btn-xs)] px-2 text-xs has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5',
        lg: 'h-[var(--control-height-lg)] gap-1.5 px-4 has-data-[icon=inline-end]:pr-2.5 has-data-[icon=inline-start]:pl-2.5',
        icon: 'size-[var(--control-height-md)]',
        'icon-xs':
          'size-[var(--control-height-xs)] rounded-[var(--cds-radius-btn-xs)] [&_svg:not([class*=size-])]:size-3',
        'icon-sm':
          'size-[var(--control-height-sm)] rounded-[var(--cds-radius-btn-xs)] [&_svg:not([class*=size-])]:size-3.5',
        'icon-lg': 'size-[var(--control-height-lg)]',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
)

export type ButtonVariants = VariantProps<typeof buttonVariants>

export type ButtonProps = React.ComponentProps<'button'> &
  ButtonVariants & {
    /** 用子元素（如链接）渲染，保留按钮样式与可访问性语义 */
    asChild?: boolean
  }

function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Component = asChild ? Slot.Root : 'button'

  return (
    <Component
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
