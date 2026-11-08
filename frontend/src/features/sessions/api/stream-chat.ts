import { ApiError, isSseEventType, readSseStream, type SseMessage } from '@/core/http'

import { INVALID_RESPONSE_MESSAGE, sendAgentRequest } from './request'
import type { ChatCitation, ChatRequest, ChatStreamEvent, StreamChatOptions } from './types'

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const toText = (value: unknown, fallback = ''): string =>
  typeof value === 'string' ? value : fallback

/**
 * 把服务端引用数组转换为展示结构。
 *
 * 单条引用字段缺失时跳过该条而不是整帧丢弃：检索结果属于增强信息，
 * 解析失败不应影响正文渲染。
 */
const toCitations = (value: unknown): ChatCitation[] => {
  if (!Array.isArray(value)) {
    return []
  }

  const citations: ChatCitation[] = []
  for (const item of value) {
    if (!isRecord(item)) {
      continue
    }
    const sourceId = toText(item.source_id)
    if (!sourceId) {
      continue
    }
    const citation: ChatCitation = {
      sourceId,
      title: toText(item.title),
      snippet: toText(item.snippet),
    }
    if (typeof item.score === 'number') {
      citation.score = item.score
    }
    citations.push(citation)
  }
  return citations
}

const parseEventData = (data: string): Record<string, unknown> | null => {
  try {
    const parsed: unknown = JSON.parse(data)
    return isRecord(parsed) ? parsed : null
  } catch {
    // 单帧 JSON 损坏不影响后续帧，直接跳过
    return null
  }
}

/**
 * 把一帧 SSE 转换为业务事件。
 *
 * 未识别的 event 或损坏的 data 返回 null，保证新事件类型上线时旧客户端
 * 只忽略该帧而不会中断整个流。
 */
const toChatStreamEvent = (message: SseMessage): ChatStreamEvent | null => {
  const data = parseEventData(message.data)
  if (!data || !isSseEventType(message.event)) {
    return null
  }

  switch (message.event) {
    case 'token':
      return { type: 'token', text: toText(data.text) }
    case 'reasoning':
      return { type: 'reasoning', text: toText(data.text) }
    case 'tool_call':
      return {
        type: 'tool_call',
        name: toText(data.name),
        args: isRecord(data.args) ? data.args : {},
      }
    case 'tool_result': {
      const event: ChatStreamEvent = { type: 'tool_result', preview: toText(data.preview) }
      if (typeof data.name === 'string') {
        event.name = data.name
      }
      return event
    }
    case 'citations':
      return { type: 'citations', citations: toCitations(data.citations) }
    case 'done':
      return { type: 'done', threadId: toText(data.thread_id) }
    case 'error':
      return {
        type: 'error',
        code: toText(data.code, 'agent_error'),
        message: toText(data.message),
      }
  }
}

/**
 * 发起对话并以异步生成器逐帧返回 SSE 事件。
 *
 * 调用方通过 signal 取消请求；HTTP 层错误在流建立前抛出 ApiError，
 * 流建立后的错误由服务端以 error 事件返回，二者可通过 error.type 区分。
 */
export async function* streamChat(
  payload: ChatRequest,
  options: StreamChatOptions = {},
): AsyncGenerator<ChatStreamEvent> {
  const headers: Record<string, string> = {
    Accept: 'text/event-stream',
    'Content-Type': 'application/json',
  }
  if (options.idempotencyKey) {
    headers['Idempotency-Key'] = options.idempotencyKey
  }

  // 401 重放沿用同一个 Idempotency-Key，服务端可据此去重；
  // 一旦进入 readSseStream 就不再重发，避免工具调用被执行两次
  const response = await sendAgentRequest('/chat/stream', {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    signal: options.signal,
  })

  if (!response.body) {
    throw new ApiError(INVALID_RESPONSE_MESSAGE, { status: response.status })
  }

  for await (const message of readSseStream(response.body)) {
    const event = toChatStreamEvent(message)
    if (event) {
      yield event
    }
  }
}
