export interface MarkdownBlock {
    /** 块在消息内的稳定序号；流式只追加，已完成块的 ID 不会变化 */
    readonly id: string
    readonly content: string
}

const BLOCK_ID_PREFIX = 'md-block'
const OPEN_FENCE_PATTERN = /^ {0,3}(`{3,}|~{3,})/
const CLOSE_FENCE_PATTERN = /^ {0,3}(`{3,}|~{3,})[ \t]*$/

interface FenceMarker {
    readonly char: string
    readonly length: number
}

const readOpenFence = (line: string): FenceMarker | null => {
    const marker = OPEN_FENCE_PATTERN.exec(line)?.[1]
    return marker ? { char: marker.charAt(0), length: marker.length } : null
}

/**
 * 判断是否为当前围栏的闭合行。
 *
 * 闭合围栏不允许携带 info string，且长度不得短于开启围栏；
 * 否则代码块里出现的 ```js 之类的文本会被误判为结束。
 */
const isClosingFence = (line: string, open: FenceMarker): boolean => {
    const marker = CLOSE_FENCE_PATTERN.exec(line)?.[1]
    return Boolean(marker && marker.charAt(0) === open.char && marker.length >= open.length)
}

/**
 * 把流式 Markdown 切成可独立渲染的块。
 *
 * 只在「代码围栏之外的空行」处切分：已完成的块内容不再变化，渲染层用 memo
 * 固定后，每帧只需要重新解析仍在增长的尾块，避免整段文本随长度反复解析。
 * 围栏内的空行不切分，保证未闭合代码块始终作为一个整体渲染。
 */
export function splitMarkdownBlocks(source: string): MarkdownBlock[] {
    const blocks: string[] = []
    let current: string[] = []
    let openFence: FenceMarker | null = null

    const flush = (): void => {
        if (current.length > 0) {
            const content = current.join('\n').replace(/\s+$/, '')
            if (content.trim()) {
                blocks.push(content)
            }
        }
        current = []
    }

    for (const line of source.split('\n')) {
        if (openFence) {
            if (isClosingFence(line, openFence)) {
                openFence = null
            }
            current.push(line)
            continue
        }

        const fence = readOpenFence(line)
        if (fence) {
            openFence = fence
            current.push(line)
            continue
        }

        if (line.trim() === '') {
            flush()
            continue
        }

        current.push(line)
    }

    flush()

    return blocks.map((content, index) => ({
        id: `${BLOCK_ID_PREFIX}-${index}`,
        content,
    }))
}
