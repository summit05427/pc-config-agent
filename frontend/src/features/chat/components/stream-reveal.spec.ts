import { describe, expect, it } from 'vitest'

import { rehypeStreamReveal } from './stream-reveal'

interface TestNode {
    type: string
    tagName?: string
    value?: string
    properties?: Record<string, unknown>
    children?: TestNode[]
}

const textNode = (value: string): TestNode => ({ type: 'text', value })

const elementNode = (tagName: string, ...children: TestNode[]): TestNode => ({
    type: 'element',
    tagName,
    children,
})

const createRoot = (...children: TestNode[]): TestNode => ({ type: 'root', children })

const collectSpans = (node: TestNode, spans: TestNode[] = []): TestNode[] => {
    if (node.tagName === 'span') {
        spans.push(node)
    }
    node.children?.forEach((child) => collectSpans(child, spans))
    return spans
}

const spanText = (span: TestNode): string =>
    (span.children ?? []).map((child) => child.value ?? '').join('')

const reveal = (tree: TestNode): TestNode => {
    rehypeStreamReveal()(tree)
    return tree
}

describe('rehypeStreamReveal', () => {
    it('把每个非空白字符包成带动画类名的 span', () => {
        const tree = reveal(createRoot(elementNode('p', textNode('你 好'))))

        const spans = collectSpans(tree)
        expect(spans.map(spanText)).toEqual(['你', '好'])
        expect(spans[0]?.properties?.className).toEqual(['stream-char'])
    })

    it('空白保持为普通文本节点，不影响换行与字间距', () => {
        const tree = reveal(createRoot(elementNode('p', textNode('a b'))))

        const children = tree.children?.[0]?.children ?? []
        expect(children[1]).toEqual({ type: 'text', value: ' ' })
    })

    it('代码块内的文本不包裹', () => {
        const code = elementNode('code', textNode('const a = 1'))
        const tree = reveal(createRoot(elementNode('pre', code)))

        expect(collectSpans(tree)).toHaveLength(0)
        expect(code.children?.[0]?.value).toBe('const a = 1')
    })

    it('内联元素内的文本同样逐字包裹', () => {
        const tree = reveal(
            createRoot(elementNode('p', elementNode('strong', textNode('加粗')))),
        )

        expect(collectSpans(tree).map(spanText)).toEqual(['加', '粗'])
    })

    it('尾块超过上限时整体跳过，避免单帧创建过多 span', () => {
        const tree = reveal(createRoot(elementNode('p', textNode('字'.repeat(1201)))))

        expect(collectSpans(tree)).toHaveLength(0)
    })

    it('空树不会抛错', () => {
        expect(() => rehypeStreamReveal()({})).not.toThrow()
    })
})
