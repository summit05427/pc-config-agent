import { cn } from '@/shared/lib/utils'

export interface BrandMarkProps {
    /** sm 用于侧栏品牌位与消息头像，md 用于登录页、错误页的大号品牌位 */
    size?: 'sm' | 'md'
}

/**
 * 品牌标记统一引用 public/favicon.svg，标签页图标与界面 Logo 共用一份资源，
 * 避免内联 SVG 与 favicon 各自维护导致替换后界面不生效。
 */
export function BrandMark({ size = 'md' }: BrandMarkProps) {
    return (
        <img
            src="/favicon.svg"
            alt=""
            aria-hidden="true"
            className={cn('shrink-0', size === 'sm' ? 'size-6 rounded-[0.375rem]' : 'size-8 rounded-md')}
        />
    )
}
