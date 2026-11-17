// SSE 帧解析工具：与服务端 agent-service/app/api/v1/chat.py 的编码格式一一对应。
// 独立于具体业务，只负责把字节流还原成 { id, event, data } 事件。
export interface SseMessage {
  id?: string
  event: string
  data: string
}

/**
 * Agent 对话流允许的 8 类事件。
 *
 * 解析器仍返回通用 `event: string`，保证未知事件被静默忽略而不是中断整个流；
 * 业务层用 `isSseEventType` 收窄后再分发。
 */
export const SSE_EVENT_TYPES = [
  'token',
  'reasoning',
  'stage',
  'tool_call',
  'tool_result',
  'citations',
  'interrupt',
  'done',
  'error',
] as const

export type SseEventType = (typeof SSE_EVENT_TYPES)[number]

export const isSseEventType = (value: string): value is SseEventType =>
  SSE_EVENT_TYPES.some((item) => item === value)

const EVENT_SEPARATOR = '\n\n'
const DEFAULT_EVENT = 'message'
const DATA_FIELD = 'data'
const EVENT_FIELD = 'event'
const ID_FIELD = 'id'

interface ParsedChunk {
  id?: string
  event: string
  data: string
  hasData: boolean
}

// 服务端可能写入 CRLF，先统一成 LF 再按空行切分，避免 Windows 环境解析失败
const normalizeLineBreaks = (value: string): string =>
  value.replace(/\r\n/g, '\n').replace(/\r/g, '\n')

const parseChunk = (chunk: string): ParsedChunk => {
  const dataLines: string[] = []
  let event = DEFAULT_EVENT
  let id: string | undefined

  for (const line of chunk.split('\n')) {
    // 以冒号开头的是注释，本项目用作心跳（: ping），直接忽略
    if (line.startsWith(':')) {
      continue
    }

    const separatorIndex = line.indexOf(':')
    const field = separatorIndex === -1 ? line : line.slice(0, separatorIndex)
    const rawValue = separatorIndex === -1 ? '' : line.slice(separatorIndex + 1)
    // SSE 规范只去掉冒号后的第一个空格，其余空格属于内容
    const value = rawValue.startsWith(' ') ? rawValue.slice(1) : rawValue

    if (field === DATA_FIELD) {
      dataLines.push(value)
    } else if (field === EVENT_FIELD) {
      event = value || DEFAULT_EVENT
    } else if (field === ID_FIELD) {
      id = value
    }
  }

  return { id, event, data: dataLines.join('\n'), hasData: dataLines.length > 0 }
}

/**
 * 解析当前缓冲区中的完整 SSE 事件。
 *
 * @param buffer 已解码的文本缓冲区，允许包含不完整的尾部帧
 * @returns messages 为本次可解析的事件；rest 需与下一次读取的数据拼接
 */
export const parseSseBuffer = (buffer: string): { messages: SseMessage[]; rest: string } => {
  const chunks = normalizeLineBreaks(buffer).split(EVENT_SEPARATOR)
  const rest = chunks.pop() ?? ''
  const messages: SseMessage[] = []

  for (const chunk of chunks) {
    const parsed = parseChunk(chunk)
    // 没有 data 的块按规范丢弃，例如纯心跳或只有 event 的块
    if (!parsed.hasData) {
      continue
    }

    const message: SseMessage = { event: parsed.event, data: parsed.data }
    if (parsed.id !== undefined) {
      message.id = parsed.id
    }
    messages.push(message)
  }

  return { messages, rest }
}

/**
 * 逐帧读取 SSE 响应体。
 *
 * 使用 TextDecoder 的 stream 模式处理多字节字符被切分到不同 chunk 的情况；
 * 流结束时补一个分隔符，保证最后一帧即使没有空行也能被解析。
 */
export async function* readSseStream(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<SseMessage> {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    let chunk = await reader.read()
    while (!chunk.done) {
      buffer += decoder.decode(chunk.value, { stream: true })
      const parsed = parseSseBuffer(buffer)
      buffer = parsed.rest
      for (const message of parsed.messages) {
        yield message
      }
      chunk = await reader.read()
    }

    buffer += decoder.decode()
    const tail = parseSseBuffer(`${buffer}${EVENT_SEPARATOR}`)
    for (const message of tail.messages) {
      yield message
    }
  } finally {
    // 无论正常结束、异常还是调用方提前 return，都要释放锁，避免流被长期占用
    reader.releaseLock()
  }
}
