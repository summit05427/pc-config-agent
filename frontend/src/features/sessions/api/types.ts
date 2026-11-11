import type { PageResult } from '@/shared/types/http'

export interface SessionSummary {
  thread_id: string
  /** 服务端按首条用户消息生成，或由用户重命名；尚未生成时为 null */
  title?: string | null
  /** 会话级模型选择；null 表示 Auto（平台默认） */
  model_key: string | null
  last_active_at: string
  /** 置顶项在服务端排序中优先展示 */
  is_pinned?: boolean
  /** 归档项不出现在默认列表中，可通过「已归档的聊天」查看 */
  is_archived?: boolean
}

/** 置顶/归档接口返回的最新会话状态 */
export interface SessionStateResult {
  thread_id: string
  is_pinned: boolean
  is_archived: boolean
  updated_at: string | null
}

/** 历史消息的读取方向：desc 用于「先看最新一页，再向前翻」 */
export type SessionMessageOrder = 'asc' | 'desc'

export interface SessionRenameResult {
  thread_id: string
  title: string
}

/** 会话级模型选择生效后的目录快照；服务端字段为 snake_case */
export interface SessionModelInfo {
  provider: string
  model_key: string
  display_name: string
  capabilities: string[]
  context_window: number
}

/** effective=auto 时 model 为 null，表示回落到平台默认模型 */
export type SessionModelEffective = 'explicit' | 'auto'

export interface SessionModelResult {
  thread_id: string
  model_key: string | null
  effective: SessionModelEffective
  model: SessionModelInfo | null
  updated_at: string
}

export interface ToolCallRecord {
  id?: string
  name: string
  args: Record<string, unknown>
}

export interface SessionMessage {
  /** 会话内稳定消息标识（`{thread_id}:{seq}`）；反馈绑定依赖该字段，旧服务端可能缺失 */
  message_id?: string
  role: string
  content: string
  tool_calls?: ToolCallRecord[]
  name?: string
  /** 服务端写入时间；用于「显示时间」开关，旧数据可能为空 */
  created_at?: string
  /** 历史里待恢复的 HITL 中断；仅最后一条助手消息可能出现 */
  hitl?: HitlInterrupt
  /** 服务端原始结构化结果；只在接口边界存在，渲染层使用 buildResult */
  build_result?: unknown
  /** 解析后的结构化配置结果：刷新后详情面板与卡片依赖它 */
  buildResult?: BuildResult
}

export interface SessionMessagesResult extends PageResult<SessionMessage> {
  thread_id: string
}

export interface ChatRequest {
  message: string
  thread_id: string
  /** 指定 Agent Profile；省略或 null 时使用服务端默认 Profile */
  agent_id?: string | null
  /** 单次覆盖本轮的模型；省略或 null 表示沿用会话选择 / Auto */
  model?: string | null
  preferences?: ChatPreferences
  /** 重新生成：服务端替换最后一条 AI 回答，而不是追加新回合 */
  regenerate?: boolean
  /** 恢复一次 HITL 中断；与 regenerate 互斥 */
  resume?: ChatResumeRequest
}

/** 恢复 HITL 中断：interrupt_id 来自 SSE interrupt 事件，answer 按 input_schema 填写 */
export interface ChatResumeRequest {
  interrupt_id: string
  answer: Record<string, unknown>
}

/**
 * Agent 对话请求携带的偏好。
 *
 * 字段名与 Agent 的 Pydantic 模型一致（snake_case），而 Java 偏好接口用 camelCase，
 * 转换只在偏好映射处发生，避免各处手写映射。
 */
export interface ChatPreferences {
  instructions?: string | null
  reply_language?: 'auto' | 'zh-CN' | 'en-US'
  response_style?: 'concise' | 'balanced' | 'detailed'
  use_history?: boolean
}

/** RAG 检索返回的引用；服务端字段为 snake_case，展示层按需改写 */
export interface ChatCitation {
  sourceId: string
  title: string
  snippet: string
  /** 相关度 0~1；检索器未提供时省略 */
  score?: number
}

/** 兼容性结论；UNKNOWN 表示参数缺失、无法确认，不能按通过展示 */
export type BuildCompatibilityStatus = 'PASS' | 'WARNING' | 'FAIL' | 'UNKNOWN'

/**
 * 兼容性风险等级。
 *
 * BLOCKING 表示该检查项会阻断装机（前提是结论为 UNKNOWN 时仍待核验）；
 * ADVISORY 只是提示，不改变结论。
 */
export type BuildCompatibilityRiskLevel = 'BLOCKING' | 'ADVISORY'

/** 用途画像；CREATIVE / WORKSTATION / OFFICE / BALANCED 为旧版本取值 */
export type BuildWorkloadProfile =
  | 'GENERAL'
  | 'GAMING'
  | 'VIDEO_EDITING'
  | 'PROGRAMMING'
  | 'RENDERING'
  | 'AI_INFERENCE'
  | 'CREATIVE'
  | 'WORKSTATION'
  | 'OFFICE'
  | 'BALANCED'

/** 预算校验结论；服务端当前产出 WITHIN_BUDGET / OVER_BUDGET / NO_BUDGET */
export type BuildBudgetStatus = 'WITHIN_BUDGET' | 'OVER_BUDGET' | 'NO_BUDGET' | 'UNKNOWN'

export interface BuildBenchmark {
  type: string
  score: number
}

/**
 * 单个硬件条目。
 *
 * Agent 当前把 `done.build_result` 投影为 snake_case 子集，展示层在解析边界
 * 统一归一化为 camelCase。品牌、商品标题、平台、商家、价格来源等字段在
 * 后端补齐投影后自动生效；缺失时保持 null，绝不由前端推断。
 */
export interface BuildComponent {
  category: string
  /** 硬件标识；Agent 投影可能省略，缺失时无法把逐件理由关联到该行 */
  hardwareId?: string | null
  modelName: string
  specSummary: string
  priceFen: number
  purchaseUrl: string | null
  /** 商品图地址；catalog 缺失或非法时为空 */
  imageUrl?: string | null
  benchmark: BuildBenchmark | null
  /** 报价核验时间；null 表示未核验 */
  offerVerifiedAt: string | null
  brand: string | null
  title: string | null
  platform: string | null
  seller: string | null
  /** MOCK_DEMO 时必须按演示价展示，不能当作已核验报价 */
  priceSource: string | null
  priceType: string | null
  verifiedPrice: boolean | null
}

/**
 * 单个硬件的确定性选型理由。
 *
 * 理由文本由 Java 确定性生成，前端只按 `hardwareId` 匹配到硬件行原样展示，
 * 不改写、不补充、不据此推断性价比；`scoreContribution` 与 `priceFen` 是原始透传值。
 */
export interface BuildComponentReason {
  /** 硬件类别（服务端枚举名，如 GPU） */
  hardwareCategory: string
  /** 与 `BuildComponent.hardwareId` 对应的匹配键 */
  hardwareId: string
  reason: string
  /** 该件对方案总分的原始贡献，缺失时不展示 */
  scoreContribution?: number
  /** 该件价格，单位人民币分；缺失时不展示 */
  priceFen?: number
}

export interface BuildCompatibilityCheck {
  rule: string
  /** 规则 ID（如 cooler_case_height）；历史消息可能缺失 */
  ruleId?: string
  status: BuildCompatibilityStatus
  message: string
  /** 风险等级；历史消息不含该字段，缺失时不能推断为任何等级 */
  riskLevel?: BuildCompatibilityRiskLevel
}

/** `done.build_result`：结构化整机配置，供结果卡片渲染 */
export interface BuildResult {
  buildId: string | null
  components: BuildComponent[]
  totalPriceFen: number
  budgetMaxFen: number | null
  budgetStatus: BuildBudgetStatus
  /** 整体结论：服务端给出则采用，否则按 FAIL > UNKNOWN > WARNING > PASS 合并 */
  overallCompatibility: BuildCompatibilityStatus
  compatibility: BuildCompatibilityCheck[]
  reasonSummary: string
  offerDataStatus: string | null
  verifiedOfferCount: number | null
  demoOfferCount: number | null
  /** 用途画像；历史消息不含该字段，缺失时省略用途标签 */
  workloadProfile?: BuildWorkloadProfile
  /** 评分版本，如 `pc-scoring-1.0.0`；历史消息不含该字段 */
  scoringVersion?: string
  /** 逐件选型理由；历史消息不含该字段，缺失时不渲染任何理由区域 */
  componentReasons?: BuildComponentReason[]
}

/** HITL 表单字段；type 决定渲染控件，未知类型按文本输入兜底 */
export interface HitlField {
  name: string
  label: string
  type: string
  required: boolean
  /** 数值字段的最小值；仅 number 类型可能提供 */
  min?: number
  /** select / radio 的候选项 */
  options?: Array<{ value: string; label: string }>
}

/** 服务端中断载荷；只包含用户可见信息，不含内部图状态 */
export interface HitlInterrupt {
  interruptId: string
  interactionType: string
  question: string
  fields: HitlField[]
  submitLabel: string
  context: Record<string, unknown>
  schemaVersion?: string
}

/**
 * SSE 的八类事件统一转换为带判别字段的联合类型，调用方用 switch 收窄。
 *
 * `schema_version` 由服务端注入，仅用于排查与未来兼容判断；
 * 旧客户端不读取它也能正常渲染，新增字段一律为可选。
 */
export type ChatStreamEvent =
  | { type: 'token'; text: string; schema_version?: string }
  /** 思考内容增量；仅部分模型提供，与正文分离渲染 */
  | { type: 'reasoning'; text: string; schema_version?: string }
  | { type: 'tool_call'; name: string; args: Record<string, unknown>; schema_version?: string }
  | { type: 'tool_result'; name?: string; preview: string; schema_version?: string }
  | { type: 'citations'; citations: ChatCitation[]; schema_version?: string }
  /** HITL 暂停：本轮不会再有 done，前端进入等待用户回答状态 */
  | { type: 'interrupt'; interrupt: HitlInterrupt; schema_version?: string }
  /** buildResult 仅在 PC 确定性流水线成功时出现，解析失败时省略并回退 Markdown */
  | {
      type: 'done'
      threadId: string
      /** 本轮助手消息的稳定标识；缺失时该条消息不提供反馈入口 */
      messageId?: string
      buildResult?: BuildResult
      schema_version?: string
    }
  | { type: 'error'; code: string; message: string; schema_version?: string }

export interface StreamChatOptions {
  signal?: AbortSignal
  idempotencyKey?: string
}
