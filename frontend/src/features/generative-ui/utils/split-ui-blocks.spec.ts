import { describe, expect, it } from 'vitest'

import { splitUiBlocks } from './split-ui-blocks'

const openUi = (content: string) => `\`\`\`openui\n${content}\n\`\`\``

describe('splitUiBlocks', () => {
  it('纯 Markdown 返回单个 Markdown 段', () => {
    const result = splitUiBlocks('# 标题\n\n正文')
    expect(result.hasOpenUi).toBe(false)
    expect(result.segments).toHaveLength(1)
    expect(result.segments[0]).toMatchObject({ kind: 'markdown', content: '# 标题\n\n正文' })
  })

  it('单个 OpenUI 块与前后 Markdown 混排', () => {
    const content = `前置说明\n\n${openUi('root = Text("你好")')}\n\n后置说明`
    const result = splitUiBlocks(content)
    expect(result.segments.map((segment) => segment.kind)).toEqual([
      'markdown',
      'openui',
      'markdown',
    ])
    expect(result.segments[1]).toMatchObject({
      kind: 'openui',
      content: 'root = Text("你好")',
      isComplete: true,
    })
  })

  it('支持多个 OpenUI 块', () => {
    const content = `${openUi('root = Text("A")')}\n\n中间\n\n${openUi('root = Text("B")')}`
    const result = splitUiBlocks(content)
    expect(result.segments.filter((segment) => segment.kind === 'openui')).toHaveLength(2)
  })

  it('普通代码块不会被误判为 OpenUI', () => {
    const content = '```js\nconst a = 1\n```\n\n```openui\nroot = Text("X")\n```'
    const result = splitUiBlocks(content)
    expect(result.segments[0]).toMatchObject({
      kind: 'markdown',
      content: expect.stringContaining('```js'),
    })
    expect(result.segments.filter((segment) => segment.kind === 'openui')).toHaveLength(1)
  })

  it('流式中的未闭合围栏标记为未完成', () => {
    const result = splitUiBlocks('说明\n\n```openui\nroot = Stack([')
    expect(result.hasOpenUi).toBe(true)
    expect(result.hasIncompleteOpenUi).toBe(true)
    expect(result.segments.at(-1)).toMatchObject({
      kind: 'openui',
      content: 'root = Stack([',
      isComplete: false,
    })
  })

  it('未闭合的普通代码块整体保留为 Markdown', () => {
    const result = splitUiBlocks('```js\nconst a = 1')
    expect(result.hasOpenUi).toBe(false)
    expect(result.segments).toHaveLength(1)
    expect(result.segments[0]).toMatchObject({
      kind: 'markdown',
      content: expect.stringContaining('const a = 1'),
    })
  })

  it('空内容返回空段', () => {
    expect(splitUiBlocks('   \n').segments).toEqual([])
  })

  it('CRLF 归一化后仍能识别块', () => {
    const result = splitUiBlocks('说明\r\n\r\n```openui\r\nroot = Text("X")\r\n```')
    expect(result.segments.map((segment) => segment.kind)).toEqual(['markdown', 'openui'])
    expect(result.segments[1]).toMatchObject({ isComplete: true, content: 'root = Text("X")' })
  })

  it('fence info 不是 openui 时保持 Markdown', () => {
    const result = splitUiBlocks('```openui-js\nroot = Text("X")\n```')
    expect(result.hasOpenUi).toBe(false)
    expect(result.segments[0]).toMatchObject({
      kind: 'markdown',
      content: expect.stringContaining('openui-js'),
    })
  })

  it('波浪线围栏同样支持', () => {
    const result = splitUiBlocks('~~~openui\nroot = Text("X")\n~~~')
    expect(result.segments).toHaveLength(1)
    expect(result.segments[0]).toMatchObject({ kind: 'openui', isComplete: true })
  })

  it('块内出现普通字符串围栏不会提前截断', () => {
    const content = '```openui\nroot = Text("```")\n```'
    const result = splitUiBlocks(content)
    expect(result.segments).toHaveLength(1)
    expect(result.segments[0]).toMatchObject({ kind: 'openui', isComplete: true })
  })

  it('超过单条消息块数上限时多余块降级为 Markdown', () => {
    const blocks = Array.from({ length: 9 }, (_, index) => openUi(`root = Text("B${index}")`))
    const result = splitUiBlocks(blocks.join('\n\n'))

    expect(result.segments.filter((segment) => segment.kind === 'openui')).toHaveLength(8)
    expect(result.segments.at(-1)).toMatchObject({
      kind: 'markdown',
      content: expect.stringContaining('root = Text("B8")'),
    })
  })

  it('单块超过字符上限时整块降级为 Markdown', () => {
    const result = splitUiBlocks(openUi(`root = Text("${'a'.repeat(20_001)}")`))

    expect(result.hasOpenUi).toBe(false)
    expect(result.segments).toHaveLength(1)
    expect(result.segments[0]).toMatchObject({
      kind: 'markdown',
      content: expect.stringContaining('```openui'),
    })
  })

  it('单块超过行数上限时整块降级为 Markdown', () => {
    const lines = Array.from({ length: 401 }, () => 'step = Text("行")').join('\n')
    const result = splitUiBlocks(openUi(`root = Stack([\n${lines}\n])`))

    expect(result.hasOpenUi).toBe(false)
    expect(result.segments[0]).toMatchObject({ kind: 'markdown' })
  })

  it('括号嵌套超过上限时整块降级为 Markdown', () => {
    const nested = `${'Stack('.repeat(33)}${')'.repeat(33)}`
    const result = splitUiBlocks(openUi(`root = ${nested}`))

    expect(result.hasOpenUi).toBe(false)
  })

  it('字符串内的括号不参与嵌套深度计算', () => {
    const result = splitUiBlocks(openUi(`root = Text("${'('.repeat(40)}")`))

    expect(result.hasOpenUi).toBe(true)
  })

  it('未闭合尾块超过字符上限时按原文展示', () => {
    const result = splitUiBlocks(`说明\n\n\`\`\`openui\nroot = Text("${'a'.repeat(20_001)}`)

    expect(result.hasOpenUi).toBe(false)
    expect(result.hasIncompleteOpenUi).toBe(true)
    expect(result.segments.at(-1)).toMatchObject({ kind: 'markdown' })
  })
})
