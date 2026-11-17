# Agent 工作流（PC 配置）

| 项 | 内容 |
| --- | --- |
| 适用范围 | `agent-service/app/agent/pc/**` 的图结构、状态、工具、HITL 与一次对话时序 |
| 状态 | Current |
| 最后更新 | 2026-11-17 |
| 权威性 | 本文是 Agent 图与节点行为的唯一详细说明；SSE / HTTP 契约以 [docs/api-contract.md](../../api-contract.md) §6、§7 为准 |
| 主要证据 | `app/agent/pc/{graph,nodes,state,tools,hitl,quality,status,renderer}.py`、`app/agents/pc-config.yaml`、`app/services/turn.py` |

## 1. 结论先行

- 唯一生产图是 PC 配置确定性流水线：**9 个节点**（7 个业务节点 + 2 个 HITL 门控）。
- 选型由 Agent 侧 LLM 在 `build_architect` 完成；Java 只提供候选、跑分、报价、组装、兼容校验与快照等事实能力。
- Java 不提供求解/选型端点，也不再执行搜索/评分选优；不存在旧求解器或独立校验节点。
- LLM 只在 `requirement_parser`、`build_strategist`、`build_architect`、`response_generator` 四处调用；其余节点为确定性代码。
- 模型不可用时 `requirement_parser` 用正则兜底；`build_architect` **不**回退到旧求解器，直接返回结构化失败。

## 2. 图结构

```text
START
  → requirement_parser        （LLM 解析需求；失败走正则兜底）
  → requirement_validator     （代码校验；invalid / clarification / 继续）
       ├─ invalid        → response_generator → END
       ├─ clarification  → clarification_gate
       │      ├─ 仍为 clarification（HITL 关闭）→ response_generator
       │      └─ 已恢复 → requirement_parser
       └─ 其余 → build_strategist
  → build_strategist          （LLM 定策略；失败用默认策略并标记来源 DEFAULT）
  → candidate_retriever       （并发检索 8 类候选、跑分、报价统计）
       ├─ no_candidates / upstream_error → response_generator → END
       └─ 其余 → build_architect
  → build_architect           （LLM 选型 → 候选校验 → 增量校验 → Java compose → 有限修正）
       ├─ 失败 → response_generator → END
       └─ success → quality_review
  → quality_review            （确定性质量评审）
       ├─ retry → build_architect（最多 1 次）
       ├─ success + 兼容性 UNKNOWN → compatibility_gate → response_generator
       └─ 其余 → response_generator → END
```

节点常量与边定义在 `app/agent/pc/graph.py`；路由只读 `workflow_status`，不解析自然语言。

## 3. 节点职责

| 节点 | 职责 | 主要输入 | 主要输出 | 失败分支 |
| --- | --- | --- | --- | --- |
| `requirement_parser` | 把自然语言解析为 `PCRequirements` | `messages`、`preference_prompt` | `requirements` | 模型不可用/非法 → 正则与关键词兜底 |
| `requirement_validator` | 校验预算区间、用途、渲染方向与缺失槽位 | `requirements` | `validation_result` | `clarification` / `invalid` |
| `clarification_gate` | HITL：缺关键槽位时中断收集补充信息；关闭时直通 | `validation_result` | `messages`、`workflow_status` | 恢复答案非法 → `hitl_resume_invalid` |
| `build_strategist` | 产出 `BuildStrategy`（预算倾向、组件优先级、取舍原则） | `requirements` | `build_strategy`、`strategy_source` | 模型不可用/非法 → 默认策略，来源标 `DEFAULT` |
| `candidate_retriever` | 按 8 类并发调用候选工具，补充 CPU/GPU 跑分与报价统计 | `requirements` | `candidate_sets`、`candidate_pool` | `no_candidates` / `upstream_error` |
| `build_architect` | LLM 输出 `BuildProposal`；校验候选归属；可选增量校验；调 Java `compose`；失败最多修正 2 次 | 需求、策略、候选 | `build_result`、`build_proposal`、`compatibility_report` | `architect_failed` / `upstream_error` |
| `quality_review` | 确定性质量评审：CPU/GPU 档位、办公显卡上限、预算下限提示 | `requirements`、`build_result` | `quality_review`、`quality_notice`、`quality_feedback` | 可修正 → `retry`（最多 1 次） |
| `compatibility_gate` | HITL：整体兼容性 `UNKNOWN` 时确认继续或终止；关闭时直通 | `compatibility_report` | `workflow_status` | `abort` → `aborted` |
| `response_generator` | LLM 生成说明 + 确定性 Markdown/OpenUI 渲染 | 全部业务字段 | `messages`、`reason_summary` | 非成功状态走确定性失败文案 |

## 4. `build_architect` 选型流程

1. 可选先调 `search_knowledge` 获取方法学提示；RAG 未启用时返回空，不阻断。
2. LLM 按 `BuildProposal` Schema 输出恰好 8 类 `selected_components`（类别、`hardware_id`、理由）；`extra="forbid"` 禁止模型输出价格、型号文本或链接。
3. 校验每个 `hardware_id` 是否在本轮候选集内；不在候选集则记为 `CANDIDATE_NOT_IN_POOL` 并进入修正。
4. 调 `check_partial_compatibility` 对已选核心组件做增量校验；`UNKNOWN` 不算冲突。
5. 调 `compose_pc_build` 让 Java 取最低有效报价、执行 9 条完整校验、落快照。
6. 业务失败（缺报价、硬冲突、超预算）可修正；缺用户令牌、上游异常、输出截断不可修正。
7. 首次提案之外最多修正 2 次（`ARCHITECT_MAX_REPAIRS`）；仍失败则 `workflow_status=architect_failed`。
8. 模型不可用或结构化输出非法时直接失败，**不会**回退到旧求解器冒充 LLM 结果。

## 5. 工具（6 个）

| 工具 | 上游 | 超时 | 输出上限 | 单轮配额 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `search_hardware_candidates` | `GET /internal/v1/pc/hardware/candidates` | 10s | 4000 | 12 | 按类别检索候选 |
| `get_benchmark_data` | `GET /internal/v1/pc/benchmarks` | 10s | 4000 | 12 | 跑分查询 |
| `get_verified_offers` | `GET /internal/v1/pc/offers` | 10s | 6000 | 12 | 报价与来源统计 |
| `compose_pc_build` | `POST /internal/v1/pc/builds/compose` | 30s | 8000 | 3 | 非只读，必须带 `X-User-Token` |
| `check_partial_compatibility` | `POST /internal/v1/pc/builds/validate-partial` | 30s | 4000 | 4 | 任意已选子集，不落库 |
| `search_knowledge` | 进程内 Hybrid 检索（pgvector，词法+向量 RRF 融合） | 10s | 4000 | 4 | 默认关闭；关闭或缺 embedding 部署时返回空引用 |

- 所有工具经 `get_governed_tool(name)` 取得，统一获得超时、重试、角色、脱敏、截断与配额治理；节点禁止直接使用 `httpx`。
- 工具异常统一转成 `ToolExecutionError` 安全文案，内部地址与堆栈只进日志。
- `AGENT__ARCHITECT_MAX_PARTIAL_CHECKS`（默认 2）与 `AGENT__ARCHITECT_MAX_KNOWLEDGE_CALLS`（默认 2）在节点层再收一层配额。

## 6. `PCConfigState` 字段

| 字段 | 用途 |
| --- | --- |
| `messages` | 用户输入与最终 AI 正文；`turn.py` 据此落库 |
| `preference_prompt` / `use_history` | 本轮偏好片段与是否注入历史，由 `turn.py` 每轮写入 |
| `requirements` / `validation_result` | 结构化需求与校验结论 |
| `build_strategy` / `strategy_source` | 配置策略与来源（`MODEL` / `DEFAULT`） |
| `candidate_pool` / `candidate_sets` / `candidate_truncated` | 候选计数、按类别保留的决策字段、截断条数 |
| `build_proposal` / `architect_repair_count` | LLM 选型产物与修正次数 |
| `partial_compatibility_reports` / `partial_check_count` | 增量校验报告与次数 |
| `knowledge_citations` / `knowledge_call_count` | 知识检索引用与次数 |
| `build_result` / `build_failure` | Java 组装结果或结构化失败 |
| `compatibility_report` | 完整兼容性报告 |
| `quality_review` / `quality_notice` / `quality_feedback` / `quality_retry_count` | 质量评审结论与重选反馈 |
| `reason_summary` | 最终推荐说明（LLM 或确定性文案） |
| `workflow_status` | 路由与失败分支的唯一依据 |
| `tool_events` | 节点累积的工具进度，由 `turn.py` 翻译成 SSE |

状态中不保存用户令牌、服务令牌、完整 JWT 或全量商品列表；`user_token` 只存在于 `TurnRequest`。

## 7. HITL

`HITL__ENABLED` 默认 `false`；关闭时两个门控节点原样返回 `{}`。

| 门控 | 触发条件 | 交互类型 |
| --- | --- | --- |
| `clarification_gate` | `requirement_validator` 判定 `clarification`（缺预算/用途等） | `clarify_requirements` |
| `compatibility_gate` | `quality_review` 后 `workflow_status=success` 且整体兼容性 `UNKNOWN` | `confirm_compatibility` |

- 兼容性为 `PASS` / `FAIL` / `WARNING` 时不中断；`FAIL` 在 `compose` 阶段已失败，不会进入成功路径。
- 恢复复用 `POST /api/v1/chat/stream` 的 `resume` 字段，与 `regenerate=true` 互斥。
- `abort` 写入 `workflow_status=aborted`，输出固定终止文案。
- 开启 HITL 必须 `STORAGE__BACKEND=postgres`，否则启动失败；`memory` 后端无法跨进程恢复。
- 中断不发送 `done`；前端把 `interrupt` 视为本轮终态。

中断载荷示例与恢复校验错误码见 [docs/api-contract.md](../../api-contract.md) §7。

## 8. tool_events 与 SSE 映射

节点不直接发 SSE，只累积 `tool_events`，由 `turn.py` 翻译：

| 节点事件 | SSE 事件 | 字段 |
| --- | --- | --- |
| `{"phase":"start","name":...,"args":{...}}` | `tool_call` | `name`、`args` |
| `{"phase":"end","name":...,"preview":"..."}` | `tool_result` | `name`、`preview`（截断到 200 字符） |

`response_generator` 通过 LangGraph `custom` 流写入 `{"kind":"reasoning"|"token","text":...}`，`turn.py` 映射为既有 `reasoning` / `token`。正文在校验通过后分块下发，思考内容先于正文。

`done.build_result` 仅在 `workflow_status=success` 且 `build_result` 非空时出现；字段见 [docs/api-contract.md](../../api-contract.md) §7。

## 9. 质量评审

`quality.py` 是 Java 兼容性之外的确定性补充：

- GPU 价格低于 20 万分为亮机卡，不检查 CPU/GPU 比例。
- CPU 价格低于显卡价格的 15% 视为明显瓶颈；重选时门槛提高到 25%。
- 办公/影音场景显卡不超过预算的 15%，且绝对价格不超过 15 万分。
- 总价低于预算下限 80% 只提示，不强制重选。
- 最多重选 1 次；超限只输出 `quality_notice`，不阻塞结果。

## 10. 兜底、澄清与输出约束

- 非成功状态一律 `render_failure_markdown`，每个状态都有明确文案，不返回空串。
- 成功但模型不可用、返回空或文案含数字/型号/渠道时，改用确定性说明；正文仍由渲染器组装。
- 演示价存在时正文强制标注「演示价格，非真实在售」。
- `UNKNOWN` 保留为「未验证」，不折算成通过。
- `needs_clarification=true`，或预算为空且用户未明确用途 → `clarification`；预算 `<= 0` → `clarification`；Schema 校验失败 → `invalid`。
- 澄清只返回追问文本，不进入检索与选型，不产生 `build_result`。

## 11. checkpointer 与存储

- 默认 `MemorySaver`；`STORAGE__BACKEND=postgres` 时使用 `AsyncPostgresSaver` 与 `psycopg_pool`。
- 连接池必须 `autocommit=True`（`setup()` 含 `CREATE INDEX CONCURRENTLY`）。
- `thread_id` 用命名空间值（`user_id:客户端值`）；`session_messages` 只写客户端原始值。
- `turn.py` 在流结束后 `aget_state` 读取最终状态，先落库再发 `done`。

## 12. Profile 与提示词

| 字段 | 值 |
| --- | --- |
| `id` | `pc-config` |
| `system_prompt` | `pc-config-system` |
| `model.temperature` / `max_tokens` | `0.3` / `2048` |
| 工具 | 上述 6 个 |
| 默认 Profile | `AGENT__DEFAULT_PROFILE=pc-config` |

- Profile `extra="forbid"`，不能选择图；单图由 `build_agent` 固定装配。
- 提示词：`app/agent/prompts/` 下的 `pc-config-system.md`、`requirement-parser.md`、`response-generator.md`，以及 `prompts/pc/` 下的 `build-strategist.md`、`build-architect.md`。
- 解析、策略与选型均打 `TAG_NOSTREAM`，内部 JSON 不进入消息流。

## 13. 未实现与默认关闭的能力

- 多 Agent 编排、工具并行执行、人工审批流【规划中】。
- RAG 检索链路（切块 → embedding → pgvector → 词法+向量 RRF → Architect 注入 → citations）已实现，默认关闭：LiteLLM 已注册 `qwen:text-embedding-v4`（百炼，需根 `.env` 的 `QWEN_API_KEY`），配置齐备即可开启；语料为 `knowledge/cards/` 的 19 张卡片（9 张内部方法论 + 10 张数据集快照）。未完成：rerank、引用正确性的持续回归。
- MCP 仅保留经网关的客户端接缝，默认关闭【未实现业务用途】。

### 13.1 RAG 数据流（已实现，默认关闭）

```text
scripts/import_knowledge_cards.py
  → 切块 + embedding（RAG__EMBEDDING_MODEL，经 LiteLLM 调用）
  → agent_service 库 kb_documents / kb_chunks（pgvector + tsvector）
  → PgvectorRetriever（先按 user_id / roles 过滤，再跑词法与向量双通道，RRF 融合）
  → build_architect 把片段写入提示词 → state.knowledge_citations
  → turn.py 按 source_id 去重后下发 citations 事件
```

默认关闭（根 `.env` `RAG_ENABLED=false`，Compose 注入为 `RAG__ENABLED`）；开启需同时给出 `RAG_RETRIEVER_MODULE` 与 `RAG_EMBEDDING_MODEL` / `RAG_EMBEDDING_DIMENSIONS`，否则启动期拒绝。嵌入维度必须与 `kb_chunks.embedding` 的类型一致（默认 1024）。语料为 `knowledge/cards/` 的 19 张卡片，导入用 `scripts/import_knowledge_cards.py`。

## 14. 相关文档

- PC 模块总览：[README.md](../../pc-config/README.md)
- 兼容规则：[compatibility-rules.md](../../pc-config/compatibility-rules.md)
- 数据与报价：[data.md](../../pc-config/data.md)
- 评测：[testing-and-evaluation.md](../../pc-config/testing-and-evaluation.md)
- Agent 分层：[architecture.md](./architecture.md)
- 提示词目录：`app/agent/prompts/pc/`
