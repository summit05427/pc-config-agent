import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./request', () => ({
  sendAgentRequest: vi.fn(),
  INVALID_RESPONSE_MESSAGE: '响应解析失败',
}))

import { ApiError } from '@/core/http'

import { INVALID_RESPONSE_MESSAGE, sendAgentRequest } from './request'
import { streamChat } from './stream-chat'
import type { ChatRequest, ChatStreamEvent } from './types'

const createSseResponse = (body: string): Response => {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(body))
      controller.close()
    },
  })

  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

const collect = async (generator: AsyncGenerator<ChatStreamEvent>): Promise<ChatStreamEvent[]> => {
  const events: ChatStreamEvent[] = []
  for await (const event of generator) {
    events.push(event)
  }
  return events
}

const payload: ChatRequest = {
  message: '你好',
  thread_id: 'thread-1',
}

describe('streamChat', () => {
  beforeEach(() => {
    vi.mocked(sendAgentRequest).mockReset()
  })

  it('把七类 SSE 事件转换为带判别字段的业务事件', async () => {
    vi.mocked(sendAgentRequest).mockResolvedValue(
      createSseResponse(
        [
          'event: reasoning\ndata: {"text":"先分析"}\n\n',
          'event: token\ndata: {"text":"你"}\n\n',
          'event: tool_call\ndata: {"name":"search","args":{"q":"x"}}\n\n',
          'event: tool_result\ndata: {"name":"search","preview":"ok"}\n\n',
          'event: citations\ndata: {"citations":[{"source_id":"kb-1","title":"示例文档","snippet":"示例片段","score":0.9}]}\n\n',
          'event: done\ndata: {"thread_id":"thread-1"}\n\n',
          'event: error\ndata: {"code":"upstream","message":"模型不可用"}\n\n',
        ].join(''),
      ),
    )

    await expect(collect(streamChat(payload))).resolves.toEqual([
      { type: 'reasoning', text: '先分析' },
      { type: 'token', text: '你' },
      { type: 'tool_call', name: 'search', args: { q: 'x' } },
      { type: 'tool_result', name: 'search', preview: 'ok' },
      {
        type: 'citations',
        citations: [{ sourceId: 'kb-1', title: '示例文档', snippet: '示例片段', score: 0.9 }],
      },
      { type: 'done', threadId: 'thread-1' },
      { type: 'error', code: 'upstream', message: '模型不可用' },
    ])
  })

  it('done 携带 message_id 时解析为 messageId，缺失时省略该字段', async () => {
    vi.mocked(sendAgentRequest).mockResolvedValue(
      createSseResponse(
        [
          'event: done\ndata: {"thread_id":"thread-1","message_id":"thread-1:3"}\n\n',
          'event: done\ndata: {"thread_id":"thread-1"}\n\n',
        ].join(''),
      ),
    )

    const events = await collect(streamChat(payload))
    expect(events[0]).toEqual({ type: 'done', threadId: 'thread-1', messageId: 'thread-1:3' })
    expect(events[1]).toEqual({ type: 'done', threadId: 'thread-1' })
  })

  it('把 interrupt 翻译为表单结构，非法载荷按未知事件忽略', async () => {
    vi.mocked(sendAgentRequest).mockResolvedValue(
      createSseResponse(
        [
          'event: interrupt\ndata: {"interrupt_id":"int-1","interaction_type":"clarify_requirements","question":"还缺预算","input_schema":{"fields":[{"name":"budget_yuan","label":"预算","type":"number","required":true,"min":1000},{"name":"scenario","label":"用途","type":"select","required":false,"options":[{"value":"GAMING","label":"游戏"},{"value":"","label":"缺值丢弃"}]}],"submit_label":"继续"},"context":{"missing_slots":["budget_yuan"]},"schema_version":"1"}\n\n',
          'event: interrupt\ndata: {"interrupt_id":"int-2"}\n\n',
          'event: done\ndata: {"thread_id":"thread-1"}\n\n',
        ].join(''),
      ),
    )

    await expect(collect(streamChat(payload))).resolves.toEqual([
      {
        type: 'interrupt',
        interrupt: {
          interruptId: 'int-1',
          interactionType: 'clarify_requirements',
          question: '还缺预算',
          fields: [
            { name: 'budget_yuan', label: '预算', type: 'number', required: true, min: 1000 },
            {
              name: 'scenario',
              label: '用途',
              type: 'select',
              required: false,
              options: [{ value: 'GAMING', label: '游戏' }],
            },
          ],
          submitLabel: '继续',
          context: { missing_slots: ['budget_yuan'] },
          schemaVersion: '1',
        },
      },
      { type: 'done', threadId: 'thread-1' },
    ])
  })

  it('引用条目字段非法时跳过该条，保留合法引用', async () => {
    vi.mocked(sendAgentRequest).mockResolvedValue(
      createSseResponse(
        [
          'event: citations\ndata: {"citations":[{"title":"缺 source_id"},null,{"source_id":"kb-2","snippet":"片段"}]}\n\n',
          'event: done\ndata: {"thread_id":"thread-1"}\n\n',
        ].join(''),
      ),
    )

    await expect(collect(streamChat(payload))).resolves.toEqual([
      { type: 'citations', citations: [{ sourceId: 'kb-2', title: '', snippet: '片段' }] },
      { type: 'done', threadId: 'thread-1' },
    ])
  })

  it('忽略 schema_version 等新增字段，旧客户端仍能渲染', async () => {
    vi.mocked(sendAgentRequest).mockResolvedValue(
      createSseResponse(
        [
          'event: token\ndata: {"text":"你","schema_version":"1","extra":1}\n\n',
          'event: done\ndata: {"thread_id":"thread-1","schema_version":"1"}\n\n',
        ].join(''),
      ),
    )

    await expect(collect(streamChat(payload))).resolves.toEqual([
      { type: 'token', text: '你' },
      { type: 'done', threadId: 'thread-1' },
    ])
  })

  it('未知事件与损坏 JSON 被忽略，不中断后续帧', async () => {
    vi.mocked(sendAgentRequest).mockResolvedValue(
      createSseResponse(
        [
          'event: token\ndata: {"text":"第一帧"}\n\n',
          'event: unknown\ndata: {"text":"未知"}\n\n',
          'event: token\ndata: {broken\n\n',
          'event: done\ndata: {"thread_id":"thread-2"}\n\n',
        ].join(''),
      ),
    )

    await expect(collect(streamChat(payload))).resolves.toEqual([
      { type: 'token', text: '第一帧' },
      { type: 'done', threadId: 'thread-2' },
    ])
  })

  it('请求携带 SSE Accept、幂等键，并透传 AbortSignal', async () => {
    vi.mocked(sendAgentRequest).mockResolvedValue(createSseResponse(''))
    const controller = new AbortController()

    await collect(streamChat(payload, { signal: controller.signal, idempotencyKey: 'chat-1' }))

    expect(sendAgentRequest).toHaveBeenCalledWith('/chat/stream', {
      method: 'POST',
      headers: {
        Accept: 'text/event-stream',
        'Content-Type': 'application/json',
        'Idempotency-Key': 'chat-1',
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
  })

  it('响应没有可读流时抛出解析失败', async () => {
    vi.mocked(sendAgentRequest).mockResolvedValue(new Response(null, { status: 200 }))

    await expect(collect(streamChat(payload))).rejects.toMatchObject({
      message: INVALID_RESPONSE_MESSAGE,
    })
  })

  it('用户取消时原样抛出 AbortError，不转换成 error 事件', async () => {
    const abortError = new DOMException('aborted', 'AbortError')
    vi.mocked(sendAgentRequest).mockRejectedValue(abortError)

    await expect(collect(streamChat(payload))).rejects.toBe(abortError)
  })

  it('流建立前的 HTTP 错误直接抛出 ApiError', async () => {
    const apiError = new ApiError('服务器内部错误', { status: 500 })
    vi.mocked(sendAgentRequest).mockRejectedValue(apiError)

    await expect(collect(streamChat(payload))).rejects.toBe(apiError)
  })

  it('done 携带合法 build_result 时解析为结构化结果', async () => {
    vi.mocked(sendAgentRequest).mockResolvedValue(
      createSseResponse(
        [
          'event: done\ndata: {"thread_id":"thread-1","build_result":{"build_id":"b-1","components":[{"category":"CPU","model_name":"R7 7800X3D","price_fen":229900,"purchase_url":null,"benchmark":{"type":"CPU_MARK","score":28000},"offer_verified_at":"2026-01-02"}],"total_price_fen":229900,"budget_max_fen":800000,"budget_status":"WITHIN_BUDGET","compatibility":[{"rule":"CPU 插槽","status":"PASS","message":"一致"}],"reason_summary":"均衡"}}\n\n',
        ].join(''),
      ),
    )

    const events = await collect(streamChat(payload))
    expect(events).toHaveLength(1)
    expect(events[0]).toMatchObject({
      type: 'done',
      threadId: 'thread-1',
      buildResult: {
        buildId: 'b-1',
        totalPriceFen: 229900,
        budgetStatus: 'WITHIN_BUDGET',
        overallCompatibility: 'PASS',
      },
    })
  })

  it('done.build_result 透传用途、评分版本与风险等级', async () => {
    vi.mocked(sendAgentRequest).mockResolvedValue(
      createSseResponse(
        [
          'event: done\ndata: {"thread_id":"thread-1","build_result":{"build_id":"b-2","components":[{"category":"CPU","model_name":"R7 7800X3D","price_fen":229900}],"total_price_fen":229900,"budget_status":"WITHIN_BUDGET","compatibility":[{"rule":"机箱限高","status":"UNKNOWN","message":"缺少数据","risk_level":"BLOCKING"}],"reason_summary":"游戏优先","workload_profile":"GAMING","scoring_version":"pc-scoring-1.0.0"}}\n\n',
        ].join(''),
      ),
    )

    const events = await collect(streamChat(payload))
    expect(events).toHaveLength(1)
    expect(events[0]).toMatchObject({
      type: 'done',
      threadId: 'thread-1',
      buildResult: {
        workloadProfile: 'GAMING',
        scoringVersion: 'pc-scoring-1.0.0',
        compatibility: [{ rule: '机箱限高', status: 'UNKNOWN', message: '缺少数据', riskLevel: 'BLOCKING' }],
      },
    })
  })

  it('done.build_result 缺少新增字段时仍完整解析，不降级为 Markdown', async () => {
    vi.mocked(sendAgentRequest).mockResolvedValue(
      createSseResponse(
        [
          'event: done\ndata: {"thread_id":"thread-1","build_result":{"components":[{"category":"CPU","model_name":"R7"}],"compatibility":[{"rule":"CPU 插槽","status":"PASS","message":"一致"}]}}\n\n',
        ].join(''),
      ),
    )

    const events = await collect(streamChat(payload))
    expect(events).toHaveLength(1)
    const done = events[0]
    expect(done).toMatchObject({ type: 'done', threadId: 'thread-1' })
    if (done?.type !== 'done') {
      throw new Error('expected done event')
    }
    expect(done.buildResult?.workloadProfile).toBeUndefined()
    expect(done.buildResult?.scoringVersion).toBeUndefined()
    expect(done.buildResult?.compatibility[0]?.riskLevel).toBeUndefined()
  })

  it('build_result 畸形时只保留 done，线程与后续帧不受影响', async () => {
    vi.mocked(sendAgentRequest).mockResolvedValue(
      createSseResponse(
        [
          'event: done\ndata: {"thread_id":"thread-1","build_result":{"components":"bad"}}\n\n',
          'event: token\ndata: {"text":"后续"}\n\n',
        ].join(''),
      ),
    )

    const events = await collect(streamChat(payload))
    expect(events[0]).toEqual({ type: 'done', threadId: 'thread-1' })
    expect(events[1]).toEqual({ type: 'token', text: '后续' })
  })
})
