import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { MarkdownContent } from './markdown-content'

describe('MarkdownContent', () => {
    it('原始 HTML 不会进入 DOM，onerror 之类的属性不会被保留', () => {
        const { container } = render(
            <MarkdownContent content={'<img src="x" onerror="alert(1)">'} />,
        )

        expect(container.querySelector('img')).toBeNull()
        expect(container.innerHTML).not.toContain('onerror')
    })

    it('危险协议链接被过滤，但文字内容仍然展示', () => {
        const { container } = render(<MarkdownContent content={'[点我](javascript:alert(1))'} />)

        expect(container.querySelector('a[href^="javascript:"]')).toBeNull()
        expect(container.textContent).toContain('点我')
    })

    it('外链新窗口打开并补齐 noopener noreferrer', () => {
        const { container } = render(<MarkdownContent content={'[外链](https://example.com)'} />)
        const link = container.querySelector('a')

        expect(link).toHaveAttribute('href', 'https://example.com')
        expect(link).toHaveAttribute('target', '_blank')
        expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    })

    it('GFM 表格按结构化元素渲染', () => {
        const { container } = render(
            <MarkdownContent content={'| 名称 | 状态 |\n| --- | --- |\n| 搜索 | 完成 |'} />,
        )

        expect(container.querySelector('table')).not.toBeNull()
    })

    it('流式未闭合代码围栏按纯文本渲染且不抛错', () => {
        const { container } = render(<MarkdownContent content={'```js\nconst a = 1'} streaming />)

        expect(container.querySelector('pre')).not.toBeNull()
        expect(container.textContent).toContain('const a = 1')
    })

    it('流式分块渲染不丢段落，代码块保持完整', () => {
        const { container } = render(
            <MarkdownContent content={'第一段\n\n第二段\n\n```js\nconst a = 1'} streaming />,
        )

        expect(container.querySelectorAll('p')).toHaveLength(2)
        expect(container.querySelector('pre')?.textContent).toContain('const a = 1')
    })

    it('流式尾块逐字符淡入，结束后恢复纯文本', () => {
        const { container, rerender } = render(<MarkdownContent content="你好" streaming />)

        expect(container.querySelectorAll('span.stream-char')).toHaveLength(2)

        rerender(<MarkdownContent content="你好" />)

        expect(container.querySelectorAll('span.stream-char')).toHaveLength(0)
        expect(container.textContent).toBe('你好')
    })
})
