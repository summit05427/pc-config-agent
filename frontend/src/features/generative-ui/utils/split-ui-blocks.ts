import type { SplitUiBlocksResult, UiSegment } from '../types'

const OPENUI_FENCE_INFO = 'openui'
const FENCE_PATTERN = /^ {0,3}(`{3,}|~{3,})(.*)$/
const CLOSING_FENCE_PATTERN = /^ {0,3}(`{3,}|~{3,})\s*$/
const NEWLINE_PATTERN = /\r\n?/g

/** 单条消息最多渲染的 UI 块数；Agent 侧 `OPENUI__MAX_BLOCKS` 上限为 10，这里留出余量 */
const MAX_OPENUI_BLOCKS_PER_MESSAGE = 8
/** 单块 DSL 字符上限：超限整块降级为原文，避免解析与渲染开销失控 */
const MAX_OPENUI_BLOCK_CHARS = 20_000
/** 单块行数上限：正常组件树远低于该值，超限只可能是异常输出 */
const MAX_OPENUI_BLOCK_LINES = 400
/** 括号嵌套深度上限：防止模型输出深层结构拖慢解析器 */
const MAX_OPENUI_NESTING_DEPTH = 32

/**
 * 粗略扫描括号嵌套深度。
 *
 * 跳过双引号字符串，字符串里的括号不参与计数；这里只做上限保护，
 * 不校验语法，真正的语法校验仍交给 Renderer。
 */
const exceedsNestingDepth = (content: string): boolean => {
  let depth = 0
  let maxDepth = 0
  let isInString = false
  let isEscaped = false

  for (const char of content) {
    if (isInString) {
      if (isEscaped) {
        isEscaped = false
      } else if (char === '\\') {
        isEscaped = true
      } else if (char === '"') {
        isInString = false
      }
      continue
    }

    if (char === '"') {
      isInString = true
      continue
    }

    if (char === '(' || char === '[' || char === '{') {
      depth += 1
      maxDepth = Math.max(maxDepth, depth)
      if (maxDepth > MAX_OPENUI_NESTING_DEPTH) {
        return true
      }
      continue
    }

    if (char === ')' || char === ']' || char === '}') {
      depth = Math.max(0, depth - 1)
    }
  }

  return false
}

const isBlockWithinLimits = (content: string): boolean =>
  content.length <= MAX_OPENUI_BLOCK_CHARS &&
  content.split('\n').length <= MAX_OPENUI_BLOCK_LINES &&
  !exceedsNestingDepth(content)

interface FenceLine {
  readonly marker: string
  readonly info: string
}

const parseFenceLine = (line: string): FenceLine | null => {
  const match = FENCE_PATTERN.exec(line)
  const marker = match?.[1]
  if (!match || !marker) {
    return null
  }
  return { marker, info: (match[2] ?? '').trim() }
}

/** 闭合围栏必须同字符、长度不短于开启围栏，避免 ```` 被 ``` 截断 */
const isClosingFence = (line: string, marker: string): boolean => {
  const closingMarker = CLOSING_FENCE_PATTERN.exec(line)?.[1]
  if (!closingMarker) {
    return false
  }
  return closingMarker.startsWith(marker[0] ?? '') && closingMarker.length >= marker.length
}

const findClosingFence = (lines: readonly string[], from: number, marker: string): number => {
  for (let index = from; index < lines.length; index += 1) {
    const line = lines[index]
    if (line !== undefined && isClosingFence(line, marker)) {
      return index
    }
  }
  return -1
}

/**
 * 把 Assistant 文本切成 Markdown 段与 OpenUI 块。
 *
 * 纯函数、无副作用：实时消息与历史消息都调用同一份实现。
 * 普通代码块整体保留在 Markdown 段中，只有 info 恰好为 `openui` 的围栏才会成为 UI 块。
 */
export function splitUiBlocks(rawContent: string): SplitUiBlocksResult {
  const content = rawContent.replace(NEWLINE_PATTERN, '\n')
  if (content.trim().length === 0) {
    return { segments: [], hasOpenUi: false, hasIncompleteOpenUi: false }
  }

  const lines = content.split('\n')
  const lineStarts: number[] = []
  let cursor = 0
  for (const line of lines) {
    lineStarts.push(cursor)
    cursor += line.length + 1
  }

  const segments: UiSegment[] = []
  let pendingMarkdownStart = 0
  let index = 0
  let hasOpenUi = false
  let hasIncompleteOpenUi = false
  let openUiBlockCount = 0

  const pushMarkdown = (start: number, end: number): void => {
    if (end <= start) {
      return
    }
    const value = content.slice(start, end)
    if (value.trim().length === 0) {
      return
    }
    segments.push({
      kind: 'markdown',
      id: `markdown-${start}`,
      content: value,
      startOffset: start,
    })
  }

  while (index < lines.length) {
    const line = lines[index]
    if (line === undefined) {
      break
    }

    const fence = parseFenceLine(line)
    if (!fence) {
      index += 1
      continue
    }

    // 普通代码块（js、json 等）不参与切分，跳过其内容后继续扫描后面的围栏
    if (fence.info.toLowerCase() !== OPENUI_FENCE_INFO) {
      const closeIndex = findClosingFence(lines, index + 1, fence.marker)
      index = closeIndex === -1 ? lines.length : closeIndex + 1
      continue
    }

    const blockStart = lineStarts[index] ?? 0
    const closeIndex = findClosingFence(lines, index + 1, fence.marker)

    if (closeIndex === -1) {
      const blockContent = lines.slice(index + 1).join('\n')
      // 未闭合尾块已超过块数或规模上限：不再等待渲染，直接按原文展示
      if (
        openUiBlockCount >= MAX_OPENUI_BLOCKS_PER_MESSAGE ||
        !isBlockWithinLimits(blockContent)
      ) {
        pushMarkdown(pendingMarkdownStart, content.length)
        return { segments, hasOpenUi, hasIncompleteOpenUi: true }
      }

      pushMarkdown(pendingMarkdownStart, blockStart)
      hasOpenUi = true
      hasIncompleteOpenUi = true
      segments.push({
        kind: 'openui',
        id: `openui-${blockStart}`,
        content: blockContent,
        startOffset: blockStart,
        isComplete: false,
      })
      return { segments, hasOpenUi, hasIncompleteOpenUi }
    }

    const blockContent = lines.slice(index + 1, closeIndex).join('\n')
    // 超限块整段保留在 Markdown 中（含围栏），由 Markdown 渲染为代码块
    if (
      openUiBlockCount >= MAX_OPENUI_BLOCKS_PER_MESSAGE ||
      !isBlockWithinLimits(blockContent)
    ) {
      index = closeIndex + 1
      continue
    }

    pushMarkdown(pendingMarkdownStart, blockStart)
    hasOpenUi = true
    openUiBlockCount += 1
    segments.push({
      kind: 'openui',
      id: `openui-${blockStart}`,
      content: blockContent,
      startOffset: blockStart,
      isComplete: true,
    })
    pendingMarkdownStart = Math.min(
      (lineStarts[closeIndex] ?? content.length) + (lines[closeIndex]?.length ?? 0) + 1,
      content.length,
    )
    index = closeIndex + 1
  }

  pushMarkdown(pendingMarkdownStart, content.length)
  return { segments, hasOpenUi, hasIncompleteOpenUi }
}
