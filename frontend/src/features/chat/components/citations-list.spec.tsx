import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { CitationsList } from './citations-list'

describe('CitationsList', () => {
    it('没有引用时不渲染任何节点', () => {
        const { container } = render(<CitationsList citations={[]} />)

        expect(container).toBeEmptyDOMElement()
    })

    it('默认折叠，展开后展示标题、片段与相关度', async () => {
        render(
            <CitationsList
                citations={[
                    {
                        sourceId: 'doc-1',
                        title: '官方规格表',
                        snippet: '该主板支持 AM5 插槽',
                        score: 0.82,
                    },
                ]}
            />,
        )

        const toggle = screen.getByRole('button', { name: '引用来源（1）' })
        expect(toggle).toHaveAttribute('aria-expanded', 'false')
        expect(screen.queryByText('该主板支持 AM5 插槽')).toBeNull()

        await userEvent.click(toggle)

        expect(toggle).toHaveAttribute('aria-expanded', 'true')
        expect(screen.getByText('1. 官方规格表')).toBeInTheDocument()
        expect(screen.getByText('该主板支持 AM5 插槽')).toBeInTheDocument()
        expect(screen.getByText('相关度 82%')).toBeInTheDocument()
    })

    it('标题缺失时退回 sourceId，相关度缺失时不展示', async () => {
        render(
            <CitationsList
                citations={[{ sourceId: 'doc-2', title: '', snippet: '未命名来源的片段' }]}
            />,
        )

        await userEvent.click(screen.getByRole('button', { name: '引用来源（1）' }))

        expect(screen.getByText('1. doc-2')).toBeInTheDocument()
        expect(screen.queryByText(/相关度/)).toBeNull()
    })
})
