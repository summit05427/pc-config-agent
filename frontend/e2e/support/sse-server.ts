import http from 'node:http'
import type { AddressInfo } from 'node:net'

/**
 * SSE 测试服务。
 *
 * fulfill 只能一次性返回整段响应，无法模拟逐帧时序与客户端中止；
 * 因此把 /chat/stream 改写到本地 Node HTTP 服务，用真实分块写入模拟流。
 */

const APP_ORIGIN = 'http://localhost:5273'

export type SseScenario = 'token' | 'tools' | 'error' | 'stop' | 'build' | 'no-solution' | 'hitl'

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

/**
 * 八件配置的视觉验收数据。
 *
 * 金额一律整数分；其中一件标为 `MOCK_DEMO`，用于验证「演示价」提示确实出现，
 * 而不是只在正文里写一句免责声明。
 */
const BUILD_RESULT: Record<string, unknown> = {
  build_id: 'build-e2e-0001',
  workload_profile: 'GAMING',
  total_price_fen: 1_059_200,
  budget_max_fen: 1_200_000,
  budget_status: 'WITHIN_BUDGET',
  overall_status: 'WARNING',
  offer_data_status: 'MIXED_DEMO',
  verified_offer_count: 6,
  demo_offer_count: 2,
  reason_summary: '预算优先给显卡，CPU 与主板保持同代平台，其余配件满足功耗与风道要求。',
  components: [
    {
      category: 'CPU',
      model_name: 'Intel Core i5-14600KF',
      spec_summary: '14 核 20 线程 / 最高 5.3GHz / LGA1700',
      price_fen: 249_900,
      price_source: 'VERIFIED',
      verified_price: true,
      purchase_url: 'https://example.com/cpu',
    },
    {
      category: 'MOTHERBOARD',
      model_name: '微星 B760M MORTAR WIFI',
      spec_summary: 'B760 / mATX / DDR5 双通道',
      price_fen: 129_900,
      price_source: 'VERIFIED',
      verified_price: true,
      purchase_url: 'https://example.com/mb',
    },
    {
      category: 'MEMORY',
      model_name: '金士顿 FURY 16GB×2 DDR5-6000',
      spec_summary: '32GB / DDR5-6000 / CL30',
      price_fen: 79_900,
      price_source: 'VERIFIED',
      verified_price: true,
      purchase_url: 'https://example.com/ram',
    },
    {
      category: 'GPU',
      hardware_id: 'gpu-4070s',
      model_name: '影驰 RTX 4070 SUPER 金属大师',
      spec_summary: '12GB GDDR6X / 双风扇 / 长约 305mm',
      price_fen: 459_900,
      price_source: 'MOCK_DEMO',
      verified_price: false,
    },
    {
      category: 'PSU',
      model_name: '振华 LEADEX III 750W',
      spec_summary: '750W / 金牌 / 全模组',
      price_fen: 59_900,
      price_source: 'VERIFIED',
      verified_price: true,
      purchase_url: 'https://example.com/psu',
    },
    {
      category: 'CASE',
      model_name: '酷冷至尊 MB520',
      spec_summary: 'ATX / 显卡限长 410mm',
      price_fen: 39_900,
      price_source: 'VERIFIED',
      verified_price: true,
      purchase_url: 'https://example.com/case',
    },
    {
      category: 'COOLER',
      model_name: '利民 PA120 SE',
      spec_summary: '双塔六热管 / 高度 155mm',
      price_fen: 25_900,
      price_source: 'VERIFIED',
      verified_price: true,
      purchase_url: 'https://example.com/cooler',
    },
    {
      category: 'STORAGE',
      model_name: '致钛 TiPlus7100 1TB',
      spec_summary: 'PCIe 4.0 / 顺序读 7000MB/s',
      price_fen: 44_900,
      price_source: 'MOCK_DEMO',
      verified_price: false,
    },
  ],
  compatibility: [
    {
      rule: 'CPU_SOCKET_MATCH',
      status: 'PASS',
      risk_level: 'BLOCKING',
      message: 'LGA1700 与主板插槽一致',
    },
    {
      rule: 'PSU_HEADROOM',
      status: 'WARNING',
      risk_level: 'ADVISORY',
      message: '整机峰值功耗约为电源额定的 78%，余量偏紧',
    },
  ],
  component_reasons: [
    {
      hardware_id: 'gpu-4070s',
      hardware_category: 'GPU',
      reason: '游戏用途下显卡决定帧率，4070 SUPER 在两万元内性价比最高。',
    },
  ],
}

/** 澄清门控载荷：字段与服务端 `input_schema` 一致，直接驱动表单渲染 */
const HITL_CLARIFY: Record<string, unknown> = {
  interrupt_id: 'int-e2e-clarify',
  interaction_type: 'clarify_requirements',
  schema_version: '1',
  question: '还差两个信息才能求解，补齐后我继续。',
  input_schema: {
    submit_label: '提交并继续',
    fields: [
      { name: 'budget_yuan', label: '预算（元）', type: 'number', required: true, min: 1000 },
      {
        name: 'scenario',
        label: '主要用途',
        type: 'select',
        required: true,
        options: [
          { value: 'GAMING', label: '游戏' },
          { value: 'PROGRAMMING', label: '编程开发' },
        ],
      },
    ],
  },
  context: { missing_slots: ['budget_max_fen', 'scenario'] },
}

/** 各场景的帧时序：token 留出可观察的间隔，tools 留出点击展开轨迹的时间 */
const playScenario = async (
  response: http.ServerResponse,
  scenario: SseScenario,
  body: string,
  round: number,
): Promise<void> => {
  response.writeHead(200, {
    'content-type': 'text/event-stream',
    'cache-control': 'no-cache',
    connection: 'keep-alive',
    'access-control-allow-origin': APP_ORIGIN,
  })

  const threadId = readThreadId(body)

  try {
    if (scenario === 'build') {
      writeEvent(response, 'token', { text: '按 12000 元预算和游戏用途，给你这套八件配置。' })
      await delay(200)
      writeEvent(response, 'done', { thread_id: threadId, build_result: BUILD_RESULT })
      return
    }

    // 无解场景只产出确定性文案，绝不下发 build_result：卡片一旦出现就说明有方案
    if (scenario === 'no-solution') {
      writeEvent(response, 'token', { text: '按 8000 元预算在当前数据里没有可行方案。' })
      await delay(200)
      writeEvent(response, 'token', { text: '最低可行总价约 ¥10,592.00，需要放宽预算后才能求解。' })
      await delay(150)
      writeEvent(response, 'done', { thread_id: threadId })
      return
    }

    // 同一会话有两轮：首轮中断等用户填写，提交后（round >= 1）正常收尾
    if (scenario === 'hitl') {
      if (round === 0) {
        writeEvent(response, 'token', { text: '还需要确认预算和用途。' })
        await delay(200)
        writeEvent(response, 'interrupt', HITL_CLARIFY)
        return
      }
      writeEvent(response, 'token', { text: '收到，按 8000 元游戏用途继续求解。' })
      await delay(150)
      writeEvent(response, 'done', { thread_id: threadId })
      return
    }

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
  // hitl 场景需要两轮：首轮中断、提交后收尾，用计数器区分同一服务实例上的第几次请求
  let hitlRound = 0

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
      const round = scenario === 'hitl' ? hitlRound++ : 0
      void playScenario(response, scenario, body, round).catch(() => {
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
