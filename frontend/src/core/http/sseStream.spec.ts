import { describe, expect, it } from 'vitest'

import { isSseEventType, parseSseBuffer, readSseStream, type SseMessage } from './sseStream'

const collect = async (stream: ReadableStream<Uint8Array>): Promise<SseMessage[]> => {
  const messages: SseMessage[] = []
  for await (const message of readSseStream(stream)) {
    messages.push(message)
  }
  return messages
}

const createStream = (chunks: Uint8Array[]): ReadableStream<Uint8Array> =>
  new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(chunk)
      }
      controller.close()
    },
  })

describe('isSseEventType', () => {
  it('只接受约定的七类事件', () => {
    expect(isSseEventType('token')).toBe(true)
    expect(isSseEventType('reasoning')).toBe(true)
    expect(isSseEventType('tool_call')).toBe(true)
    expect(isSseEventType('tool_result')).toBe(true)
    expect(isSseEventType('citations')).toBe(true)
    expect(isSseEventType('done')).toBe(true)
    expect(isSseEventType('error')).toBe(true)
    expect(isSseEventType('message')).toBe(false)
  })
})

describe('parseSseBuffer', () => {
  it('解析 id、event 与 data', () => {
    const { messages, rest } = parseSseBuffer('id: 1\nevent: token\ndata: {"text":"hi"}\n\n')

    expect(rest).toBe('')
    expect(messages).toEqual([{ id: '1', event: 'token', data: '{"text":"hi"}' }])
  })

  it('兼容 CRLF 换行', () => {
    const { messages } = parseSseBuffer('event: done\r\ndata: {"thread_id":"t1"}\r\n\r\n')

    expect(messages).toEqual([{ event: 'done', data: '{"thread_id":"t1"}' }])
  })

  it('忽略注释心跳行', () => {
    const { messages } = parseSseBuffer(': ping\n\nevent: token\ndata: ok\n\n')

    expect(messages).toEqual([{ event: 'token', data: 'ok' }])
  })

  it('多行 data 用换行拼接', () => {
    const { messages } = parseSseBuffer('data: line1\ndata: line2\n\n')

    expect(messages).toEqual([{ event: 'message', data: 'line1\nline2' }])
  })

  it('保留不完整的尾部帧', () => {
    const { messages, rest } = parseSseBuffer('event: token\ndata: partial')

    expect(messages).toEqual([])
    expect(rest).toBe('event: token\ndata: partial')
  })

  it('丢弃没有 data 字段的块', () => {
    const { messages } = parseSseBuffer('event: token\n\n')

    expect(messages).toEqual([])
  })
})

describe('readSseStream', () => {
  it('跨 chunk 拼接并解析多帧', async () => {
    const encoder = new TextEncoder()
    const stream = createStream([
      encoder.encode('event: token\ndata: {"text":"你'),
      encoder.encode('好"}\n\nevent: done\ndata: {"thread_id":"t1"}\n\n'),
    ])

    await expect(collect(stream)).resolves.toEqual([
      { event: 'token', data: '{"text":"你好"}' },
      { event: 'done', data: '{"thread_id":"t1"}' },
    ])
  })

  it('UTF-8 字符被字节切分时仍能正确解码', async () => {
    const bytes = new TextEncoder().encode('data: 你好\n\n')
    const stream = createStream([bytes.slice(0, 7), bytes.slice(7)])

    await expect(collect(stream)).resolves.toEqual([{ event: 'message', data: '你好' }])
  })

  it('流结束时补全没有空行的最后一帧', async () => {
    const stream = createStream([new TextEncoder().encode('event: done\ndata: {}')])

    await expect(collect(stream)).resolves.toEqual([{ event: 'done', data: '{}' }])
  })

  it('流读取中断时抛出原始错误并释放读取锁', async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('event: token\ndata: first\n\n'))
      },
      // 首个 chunk 消费完后再报错，保证断言能覆盖「已产出部分帧后中断」的场景
      pull(controller) {
        controller.error(new Error('stream aborted'))
      },
    })

    const messages: SseMessage[] = []
    await expect(async () => {
      for await (const message of readSseStream(stream)) {
        messages.push(message)
      }
    }).rejects.toThrow('stream aborted')

    expect(messages).toEqual([{ event: 'token', data: 'first' }])
    expect(stream.locked).toBe(false)
  })
})
