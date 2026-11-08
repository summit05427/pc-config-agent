import http from 'node:http'
import type { AddressInfo } from 'node:net'

/**
 * SSE 测试服务。
 *
 * fulfill 只能一次性返回整段响应，无法模拟逐帧时序与客户端中止；
 * 因此把 /chat/stream 改写到本地 Node HTTP 服务，用真实分块写入模拟流。
 */

const APP_ORIGIN = 'http://localhost:5273'

export type SseScenario = 'token' | 'tools' | 'error' | 'stop'

const readThreadId = (body: string): string => {
  try {
    const parsed: unknown = JSON.parse(body)
    if (typeof parsed === 'object' && parsed !== null && 'thread_id' in parsed) {
      const threadId = (parsed as { thread_id?: unknown }).thread_id
      return typeof threadId === 'string' ? threadId : 'thread-e2e'
    }
  } catch {
    // 请求体损坏时用固定 ID，测试仍能验证 SSE 结构而不必中断
  }
  return 'thread-e2e'
}

const writeEvent = (
  response: http.ServerResponse,
  event: string,
  data: Record<string, unknown>,
): boolean => {
  if (response.destroyed || response.writableEnded) {
    return false
  }
  response.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
  return true
}

const delay = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms))

/** 各场景的帧时序：token 留出可观察的间隔，tools 留出点击展开轨迹的时间 */
const playScenario = async (
  response: http.ServerResponse,
  scenario: SseScenario,
  body: string,
): Promise<void> => {
  response.writeHead(200, {
    'content-type': 'text/event-stream',
    'cache-control': 'no-cache',
    connection: 'keep-alive',
    'access-control-allow-origin': APP_ORIGIN,
  })

  const threadId = readThreadId(body)

  try {
    if (scenario === 'token') {
      writeEvent(response, 'token', { text: '你好' })
      // 两段 token 的间隔要明显大于断言轮询周期：并行跑多个 worker 时页面首帧
      // 可能延迟数百毫秒，间隔过短会让「只看到第一段」的断言偶发失败
      await delay(1200)
      writeEvent(response, 'token', { text: '，世界' })
      await delay(150)
      writeEvent(response, 'done', { thread_id: threadId })
      return
    }

    if (scenario === 'tools') {
      writeEvent(response, 'token', { text: '先检索一下。' })
      await delay(200)
      writeEvent(response, 'tool_call', { name: 'search', args: { query: 'agent' } })
      await delay(400)
      writeEvent(response, 'tool_result', { name: 'search', preview: '检索完成' })
      await delay(1200)
      writeEvent(response, 'token', { text: '检索完成，这是结论。' })
      await delay(150)
      writeEvent(response, 'done', { thread_id: threadId })
      return
    }

    if (scenario === 'error') {
      writeEvent(response, 'token', { text: '已生成部分内容' })
      await delay(200)
      writeEvent(response, 'error', { code: 'upstream_error', message: '模型服务不可用' })
      return
    }

    // stop 场景持续产出，直到客户端中止后写入失败才退出
    writeEvent(response, 'token', { text: '已生成内容' })
    for (let index = 0; index < 20; index += 1) {
      await delay(150)
      if (!writeEvent(response, 'token', { text: `（续${index}）` })) {
        return
      }
    }
    writeEvent(response, 'done', { thread_id: threadId })
  } finally {
    response.end()
  }
}

export interface SseServerHandle {
  readonly url: string
  readonly close: () => Promise<void>
  /** 客户端在场景自然结束前断开连接的记录，按请求体里的 thread_id 归类 */
  readonly abortedThreadIds: readonly string[]
}

export const startSseServer = async (): Promise<SseServerHandle> => {
  const abortedThreadIds: string[] = []

  const server = http.createServer((request, response) => {
    const target = new URL(request.url ?? '/', APP_ORIGIN)
    const scenario = (target.searchParams.get('scenario') ?? 'token') as SseScenario
    let body = ''

    request.on('data', (chunk: Buffer) => {
      body += chunk.toString()
    })
    request.on('end', () => {
      // 场景正常写完 done 才会调用 end()，因此 close 时 writableEnded 仍为 false
      // 只可能是客户端中途断开——这正是 abort 生效的判据
      response.on('close', () => {
        if (!response.writableEnded) {
          abortedThreadIds.push(readThreadId(body))
        }
      })
      void playScenario(response, scenario, body).catch(() => {
        // 客户端停止后写入会失败，这是测试要覆盖的正常路径
      })
    })
  })

  await new Promise<void>((resolve) => {
    server.listen(0, '127.0.0.1', resolve)
  })

  const address = server.address()
  if (!address || typeof address === 'string') {
    throw new Error('SSE 测试服务未能获得监听端口')
  }
  const { port } = address as AddressInfo

  return {
    url: `http://127.0.0.1:${port}/stream`,
    close: () =>
      new Promise<void>((resolve) => {
        server.closeAllConnections()
        server.close(() => resolve())
      }),
    get abortedThreadIds() {
      return [...abortedThreadIds]
    },
  }
}
