import { describe, expect, it } from 'vitest'

import { splitMarkdownBlocks } from './markdown-blocks'

describe('splitMarkdownBlocks', () => {
    it('按空行切分普通段落，并去掉首尾空块', () => {
        const blocks = splitMarkdownBlocks('\n\n第一段\n\n第二段\n\n')

        expect(blocks.map((block) => block.content)).toEqual(['第一段', '第二段'])
        expect(blocks.map((block) => block.id)).toEqual(['md-block-0', 'md-block-1'])
    })

    it('未闭合的代码围栏内部的空行不切分', () => {
        const blocks = splitMarkdownBlocks('```js\nconst a = 1\n\nconst b = 2')

        expect(blocks).toHaveLength(1)
        expect(blocks[0]?.content).toContain('const b = 2')
    })

    it('已闭合代码块后的空行仍可作为切分点', () => {
        const blocks = splitMarkdownBlocks('```js\nconst a = 1\n```\n\n后面的说明')

        expect(blocks.map((block) => block.content)).toEqual([
            '```js\nconst a = 1\n```',
            '后面的说明',
        ])
    })

    it('流式追加只影响尾块，已完成块的内容与 ID 保持稳定', () => {
        const before = splitMarkdownBlocks('第一段\n\n正在输')
        const after = splitMarkdownBlocks('第一段\n\n正在输入更多')

        expect(after[0]).toEqual(before[0])
        expect(after[1]?.id).toBe(before[1]?.id)
        expect(after[1]?.content).toBe('正在输入更多')
    })

    it('仅空白输入返回空块列表', () => {
        expect(splitMarkdownBlocks('  \n\n\t\n')).toEqual([])
    })
})
