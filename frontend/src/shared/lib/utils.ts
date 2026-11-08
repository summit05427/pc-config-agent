import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * 合并组件类名：clsx 处理条件拼接，tailwind-merge 解决同类 Tailwind
 * 工具类冲突（后写的覆盖先写的），避免组件库样式被调用方意外叠加。
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
