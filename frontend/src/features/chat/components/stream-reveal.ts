/** HAST 节点最小结构：只声明本插件会读写到的字段 */
interface HastNode {
    type: string
    tagName?: string
    value?: string
    properties?: Record<string, unknown>
    children?: HastNode[]
}

const SKIP_TAGS = new Set(['code', 'pre', 'script', 'style'])
const REVEAL_CLASS_NAME = 'stream-char'
/** 尾块超过该长度后放弃逐字动画：避免单帧创建上千个 span 把渲染预算吃满 */
const MAX_REVEAL_CHARS = 1200

const isSkippedElement = (node: HastNode): boolean =>
    node.type === 'element' && node.tagName !== undefined && SKIP_TAGS.has(node.tagName)

const countTextLength = (node: HastNode): number => {
    if (node.type === 'text') {
        return node.value?.length ?? 0
    }
    if (isSkippedElement(node)) {
        return 0
    }
    return node.children?.reduce((total, child) => total + countTextLength(child), 0) ?? 0
}

const createRevealSpan = (char: string): HastNode => ({
    type: 'element',
    tagName: 'span',
    properties: { className: [REVEAL_CLASS_NAME] },
    children: [{ type: 'text', value: char }],
})

/**
 * 把文本节点拆成「普通空白 + 逐字符 span」。
 *
 * 空白不包裹：保留浏览器正常的换行与字间距；每个非空白字符单独成 span，
 * 首次挂载时播放一次 CSS 动画，后续追加的字符才会继续淡入。
 */
const wrapTextNode = (value: string): HastNode[] => {
    const nodes: HastNode[] = []
    let whitespace = ''

    const flushWhitespace = (): void => {
        if (!whitespace) {
            return
        }
        nodes.push({ type: 'text', value: whitespace })
        whitespace = ''
    }

    for (const char of value) {
        if (char.trim() === '') {
            whitespace += char
            continue
        }
        flushWhitespace()
        nodes.push(createRevealSpan(char))
    }

    flushWhitespace()
    return nodes
}

const transformChildren = (node: HastNode): void => {
    if (!node.children || node.children.length === 0) {
        return
    }

    const nextChildren: HastNode[] = []
    for (const child of node.children) {
        if (child.type === 'text') {
            nextChildren.push(...wrapTextNode(child.value ?? ''))
            continue
        }
        if (isSkippedElement(child)) {
            nextChildren.push(child)
            continue
        }
        transformChildren(child)
        nextChildren.push(child)
    }

    node.children = nextChildren
}

/**
 * 流式尾块的逐字符渐显 rehype 插件。
 *
 * 只在文本节点上注入 span，不改变 Markdown 结构，也不进入代码块；
 * 元素白名单需要允许 `span`，原始 HTML 仍由 `skipHtml` 丢弃。
 * 依赖 React 按索引复用同级节点：已出现的字符保持自己的动画进度，
 * 只有新追加的字符会挂载新 span 并播放动画。
 */
export function rehypeStreamReveal(): (tree: unknown) => void {
    return (tree) => {
        const root = tree as HastNode
        if (countTextLength(root) > MAX_REVEAL_CHARS) {
            return
        }
        transformChildren(root)
    }
}
