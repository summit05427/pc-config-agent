import { memo, useMemo } from 'react'
import Markdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { cn } from '@/shared/lib/utils'

import { splitMarkdownBlocks } from './markdown-blocks'
import { rehypeStreamReveal } from './stream-reveal'

/** 只放行确定安全的协议；站内相对路径单独判断，避免把 //evil.com 当成相对地址 */
const SAFE_PROTOCOLS = new Set(['http:', 'https:', 'mailto:'])

const isSiteRelativeUrl = (url: string): boolean =>
    (url.startsWith('/') && !url.startsWith('//')) ||
    url.startsWith('./') ||
    url.startsWith('../') ||
    url.startsWith('#')

/**
 * URL 白名单。
 *
 * 返回 null 时 react-markdown 会直接丢弃该属性，因此 javascript:/data: 等协议
 * 既不会进入 DOM，也不会被浏览器当作可点击目标。
 */
export const sanitizeUrl = (url: string): string | null => {
    const trimmed = url.trim()
    if (!trimmed) {
        return null
    }
    if (isSiteRelativeUrl(trimmed)) {
        return trimmed
    }

    try {
        const parsed = new URL(trimmed)
        return SAFE_PROTOCOLS.has(parsed.protocol) ? trimmed : null
    } catch {
        return null
    }
}

const isExternalUrl = (url: string): boolean => /^https?:/i.test(url)

const MARKDOWN_COMPONENTS: Components = {
    a({ href, children }) {
        if (!href) {
            return <span>{children}</span>
        }

        // 外链一律新窗口打开，并阻断来源信息；站内链接保持当前窗口行为
        return isExternalUrl(href) ? (
            <a href={href} target="_blank" rel="noopener noreferrer">
                {children}
            </a>
        ) : (
            <a href={href}>{children}</a>
        )
    },
    img({ src, alt }) {
        if (!src) {
            return null
        }
        return <img src={src} alt={alt ?? ''} loading="lazy" />
    },
    // 宽表在窄屏上横向滚动，避免把整段正文撑出可视区
    table({ children }) {
        return (
            <div className="overflow-x-auto">
                <table>{children}</table>
            </div>
        )
    },
}

/**
 * 模型输出的 Markdown 渲染。
 *
 * 不使用 rehype-raw 与 dangerouslySetInnerHTML，原始 HTML 由 skipHtml 直接丢弃；
 * 元素白名单与 URL 白名单共同限定可渲染范围。未闭合的代码围栏由解析器按纯文本
 * 兜底，流式输出不会抛错。
 */
const ALLOWED_ELEMENTS = [
    'p',
    'br',
    'strong',
    'em',
    'del',
    'code',
    'pre',
    'blockquote',
    'a',
    'img',
    'ul',
    'ol',
    'li',
    'h1',
    'h2',
    'h3',
    'h4',
    'hr',
    'table',
    'thead',
    'tbody',
    'tr',
    'th',
    'td',
    // 仅由 rehypeStreamReveal 注入，用于逐字符淡入；原始 HTML 已被 skipHtml 丢弃
    'span',
]

export interface MarkdownContentProps {
    readonly content: string
    /** 流式输出时在文末保留光标，提示仍在生成 */
    readonly streaming?: boolean
    readonly className?: string
}

/** 插件与组件映射保持模块级稳定，避免每次渲染生成新引用 */
const REMARK_PLUGINS = [remarkGfm]
const REVEAL_PLUGINS = [rehypeStreamReveal]
const PLAIN_PLUGINS: never[] = []

interface MarkdownBlockProps {
    readonly content: string
    /** 是否对新增字符做逐字淡入；只有流式尾块会打开 */
    readonly reveal: boolean
}

/**
 * 单个 Markdown 块。
 *
 * 已完成块的内容字符串不再变化，memo 后整块跳过解析与 DOM diff；
 * 流式期间只有尾块会持续重渲染，代价从「整段文本」降到「当前段落」。
 * 逐字动画插件同样只挂在尾块上，已完成块不会保留逐字 span。
 */
const MarkdownBlock = memo(function MarkdownBlock({ content, reveal }: MarkdownBlockProps) {
    return (
        <Markdown
            remarkPlugins={REMARK_PLUGINS}
            rehypePlugins={reveal ? REVEAL_PLUGINS : PLAIN_PLUGINS}
            skipHtml
            allowedElements={ALLOWED_ELEMENTS}
            urlTransform={sanitizeUrl}
            components={MARKDOWN_COMPONENTS}
        >
            {content}
        </Markdown>
    )
})

/**
 * 模型输出的 Markdown 渲染。
 *
 * 不使用 rehype-raw 与 dangerouslySetInnerHTML，原始 HTML 由 skipHtml 直接丢弃；
 * 元素白名单与 URL 白名单共同限定可渲染范围。未闭合的代码围栏由解析器按纯文本
 * 兜底，流式输出不会抛错。
 *
 * 流式期间按空行分块增量渲染，流结束后恢复整段一次解析：
 * 增量只承担逐字观感，最终 DOM 仍与整段解析完全一致。
 */
export const MarkdownContent = memo(function MarkdownContent({
    content,
    streaming = false,
    className,
}: MarkdownContentProps) {
    const blocks = useMemo(
        () =>
            streaming
                ? splitMarkdownBlocks(content)
                : [{ id: 'md-block-full', content }],
        [content, streaming],
    )
    // 只有尾块仍在增长，逐字动画挂在它身上；已完成块保持静态
    const lastBlockIndex = blocks.length - 1

    return (
        <div className={cn('prose-agent', streaming && 'stream-caret', className)}>
            {blocks.map((block, index) => (
                <MarkdownBlock
                    key={block.id}
                    content={block.content}
                    reveal={streaming && index === lastBlockIndex}
                />
            ))}
        </div>
    )
})
