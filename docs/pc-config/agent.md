# PC 配置 Agent：工作流、状态与 HITL

| 项 | 内容 |
| --- | --- |
| 状态 | 已验证（对照 2026-11-11 分支源码） |
| 最后核验 | 2026-11-11 |
| 权威性 | 本文件描述 `agent-service/app/agent/pc/` 的图结构、状态、工具、Profile 与 HITL 行为；SSE 与 HTTP 契约以 [api-contract.md](../api-contract.md) §7 为准，环境变量以[环境变量文档](../deployment/environment-variables.md)为准 |
| 主要证据 | `app/agent/pc/{graph,nodes,state,tools,hitl,renderer,status}.py`、`app/services/turn.py`、`app/api/v1/chat.py`、`app/agents/pc-config.yaml` |

## 1. 八个节点

| 节点 | 职责 | 输入 | 输出 | 失败分支 |
| --- | --- | --- | --- | --- |
| `requirement_parser` | 解析自然语言需求 | `messages`、`preference_prompt` | `requirements` | 模型失败 → 正则兜底；仍缺信息交给校验 |
| `requirement_validator` | 纯代码校验预算、场景与范围 | `requirements` | `validation_result` | `clarification` / `invalid` |
| `clarification_gate` | HITL：缺关键槽位时 `interrupt` 收集补充信息；关闭时直通 | `validation_result` | `messages`、`workflow_status` | 回答非法 → `hitl_resume_invalid` |
| `candidate_retriever` | 按 8 类并发检索候选、跑分与报价统计 | `requirements` | `candidate_pool` | `no_candidates` / `upstream_error` |
| `build_solver` | 调 Java 确定性求解 | `requirements`、`retry_count` | `build_result`、`build_failure`、`budget_report` | `no_solution` / `upstream_error` |
| `build_validator` | 调 Java 复核 8 类组合 | `build_result` | `compatibility_report` | `retry` / `compatibility_failed` |
| `compatibility_gate` | HITL：兼容性 `UNKNOWN` 时确认继续或终止；关闭时直通 | `compatibility_report` | `workflow_status` | 非法选择 → `hitl_resume_invalid` |
| `response_generator` | LLM 生成说明 + 代码渲染正文 | 全部业务字段 | `messages`、`reason_summary` | 非成功状态走确定性失败文案 |

## 2. 条件边路由

```text
START
  → requirement_parser
  → requirement_validator
       ├─ invalid → response_generator → END
       ├─ clarification → clarification_gate
       │     ├─ 仍为 clarification（HITL 关闭）→ response_generator → END
       │     └─ 已恢复 → requirement_parser
       └─ 其余 → candidate_retriever
  → candidate_retriever
       ├─ no_candidates / upstream_error → response_generator → END
       └─ 其余 → build_solver
  → build_solver
       ├─ 非 solved → response_generator → END
       └─ solved → build_validator
  → build_validator
       ├─ retry → build_solver（最多 1 次）
       ├─ SUCCESS + UNKNOWN → compatibility_gate → response_generator → END
       └─ 其余 → response_generator → END
```

- 路由只读 `workflow_status`，不解析自然语言；状态常量集中在 `status.py`。
- `build_validator` 在状态不是 `solved` 时直接返回空更新，不覆盖已有结果。
- 门控节点无副作用，恢复时只重跑门控本身，不重放求解与落库。

## 3. 重解机制

- 校验失败且 `retry_count < AGENT__MAX_SOLVE_RETRIES`（代码默认 1，上限 2）时返回 `retry`，条件边回到 `build_solver`。
- 重解时只放宽软偏好：`retry_count > 0` 时 `require_verified_offers` 固定为 `false`；预算与兼容性约束不变。
- 达到上限仍失败则返回 `compatibility_failed`，不继续循环。

## 4. tool_events → SSE 映射

节点不直接发 SSE，只返回 `tool_events`，由 `turn.py` 翻译：

| 节点事件 | SSE 事件 | 字段 |
| --- | --- | --- |
| `{"phase":"start","name":...,"args":{...}}` | `tool_call` | `name`、`args` |
| `{"phase":"end","name":...,"preview":"..."}` | `tool_result` | `name`、`preview`（截断到 200 字符） |

- 事件类型与既有 payload 形状不变，未新增 SSE 语义。
- 成功路径实测 13 个 `tool_call` 与 13 个 `tool_result`：8 类检索 + 2 类跑分 + 1 次报价统计 + 求解 + 校验。
- `tool_events` 在状态中用列表拼接归约，节点之间不会互相覆盖。

## 5. done.build_result 组装

- 仅当 `workflow_status=success` 且 `build_result` 非空时，`build_result_payload` 才返回前端投影。
- `turn.py` 在发 `done` 前先落库，再把可选 `build_result` 挂到 `done`；失败路径不返回卡片。
- 投影包含 8 类组件、总价、预算、兼容性明细、总状态、推荐说明与 `demo_offer_count`。
- `demo_offer_count` 由逐项 `priceSource=MOCK_DEMO` 派生，不是 Java 原字段。
- 正文权威来源仍是 `token` 事件；卡片字段缺失时前端回退 Markdown。

## 6. 确定性兜底与澄清判定

- 非成功状态一律 `render_failure_markdown`，每个状态都有明确文案，不返回空串。
- 成功但模型不可用、返回空或文案含数字 / 型号 / 渠道时，改用 `_deterministic_reason`，正文仍由 `render_build_markdown` 渲染。
- 演示价存在时，正文首行与末尾都会插入「演示价格，非真实在售」声明。
- 兼容性 `UNKNOWN` 保留为「未验证」，不折算成通过。
- `needs_clarification=true`，或预算为空且用户未明确用途 → `clarification`；预算 `<= 0` → `clarification`；Schema 校验失败 → `invalid`。
- 澄清只返回追问文本，不进入检索、求解，不产生 `build_result`。

## 7. PCConfigState 字段

| 字段 | 用途 | 是否持久化 |
| --- | --- | --- |
| `messages` | 用户输入与最终 AI 正文；`turn.py` 依赖它落库 | checkpointer + `session_messages` |
| `preference_prompt` | 本轮偏好片段，由 `turn.py` 每轮显式写入 | 仅 checkpointer |
| `use_history` | 是否向模型注入历史；每轮覆盖 | 仅 checkpointer |
| `requirements` | 结构化需求（`PCRequirements.model_dump()`） | 仅 checkpointer |
| `validation_result` | 校验状态、追问文案与缺失字段 | 仅 checkpointer |
| `candidate_pool` | 8 类候选计数、目录版本、缺失类别、跑分与报价统计 | 仅 checkpointer |
| `build_result` / `build_failure` | Java 求解结果与无解原因 | 仅 checkpointer |
| `compatibility_report` | 兼容性总状态与逐条检查 | 仅 checkpointer |
| `budget_report` | 预算上限、总价与预算状态 | 仅 checkpointer |
| `reason_summary` | 最终推荐说明（LLM 或确定性文案） | 仅 checkpointer |
| `retry_count` | 已发生的重解次数 | 仅 checkpointer |
| `workflow_status` | 路由与失败分支的唯一依据 | 仅 checkpointer |
| `tool_events` | 节点累积的工具进度，由 `turn.py` 消费 | 仅 checkpointer |

状态中不保存用户令牌、服务令牌、完整 JWT 或全量商品列表；`user_token` 只存在于 `TurnRequest`。

## 8. checkpointer

- 默认 `MemorySaver`，仅测试 / 本地；`STORAGE__BACKEND=postgres` 时使用 `AsyncPostgresSaver` 与 `psycopg_pool` 连接池。
- 连接池必须 `autocommit=True`：`setup()` 含 `CREATE INDEX CONCURRENTLY`，不能在事务块执行。
- `STORAGE__AUTO_SETUP=true` 时启动即幂等建表；退出时关闭连接池并回退 `MemorySaver`。
- 图编译时注入当前 checkpointer；切换实现会清除已缓存的图，避免继续使用旧存储。
- `thread_id` 用命名空间值（`user_id:客户端值`）；`session_messages` 只写客户端原始值，两者不能混用。
- `turn.py` 在流结束后用 `aget_state` 读取最终状态，先落库再发 `done`。

## 9. 五个工具

| 工具 | 参数 | 上游 / 用途 | 超时 | 输出上限 | 单轮配额 |
| --- | --- | --- | --- | --- | --- |
| `search_hardware_candidates` | `category?` | `GET /internal/v1/pc/hardware/candidates` | 10s | 4000 | 12 |
| `get_benchmark_data` | `hardware_id?`、`category?` | `GET /internal/v1/pc/benchmarks` | 10s | 4000 | 12 |
| `get_verified_offers` | `hardware_id?`、`category?`、`verified_only=false` | `GET /internal/v1/pc/offers` | 10s | 6000 | 12 |
| `solve_pc_build` | `budget_max_fen?`、`scenario`、`min_memory_gb?`、`min_storage_gb?`、`require_verified_offers` | `POST /internal/v1/pc/builds/solve` | 25s | 8000 | 3 |
| `validate_pc_build` | 8 类组件（均必填） | `POST /internal/v1/pc/builds/validate` | 10s | 4000 | 3 |

- 重试次数未在工具注册时覆盖，统一取 `AGENT__TOOL_MAX_RETRIES`（默认 1）；只有真正重跑才计重试指标。
- 输出先转文本，再按 `AGENT__TOOL_REDACT_OUTPUT`（默认 `true`）脱敏手机号、邮箱、身份证、API Key 与 Bearer，再按 token 预算截断并追加提示。
- 单轮配额由 `ToolTurn` 的 `ContextVar` 累计；超限返回提示文本而非抛错。
- `solve_pc_build` 标记 `is_read_only=false`，必须携带 `X-User-Token`；缺少身份时返回「请重新登录」安全错误。
- 工具异常统一包成 `ToolExecutionError`，内部地址与堆栈只进日志；`get_verified_offers` 默认 `verified_only=false`，允许返回 `MOCK_DEMO` 与 `PLATFORM_OBSERVED`，由渲染层强制标注。
- 节点只通过 `get_governed_tool(name)` 取工具，禁止直接使用 `httpx`。

## 10. Profile 与 Prompt

| 字段 | 值 |
| --- | --- |
| `id` | `pc-config` |
| `display_name` | PC 配置推荐 |
| `system_prompt` | `pc-config-system` |
| `model.temperature` / `max_tokens` | `0.3` / `2048` |
| `tools` | 上述 5 个工具的完整列表 |
| 默认 Profile | `AGENT__DEFAULT_PROFILE=pc-config`（代码 `config.py`） |

- Profile 的 `extra="forbid"`，不能选择图；单图由 `build_agent` 固定装配。
- Profile 校验在启动期完成；提示词缺失、工具未注册或 id 与文件名不一致都会拒绝启动。
- `pc-config-system.md` 约束人格与硬性规则：型号、价格、链接只来自结构化结果；`UNKNOWN` 不得说通过；演示价必须标注。
- `requirement-parser.md` 只输出唯一 JSON 对象，金额为整数分，不猜测未提供的预算、容量或用途。
- `response-generator.md` 生成 2–3 句说明，禁止数字、金额、型号、品牌、SKU、链接与渠道。
- 解析与生成调用均打 `TAG_NOSTREAM`，内部 JSON 与说明不会以流式 `token` 泄漏。

## 11. HITL 触发与时序

`HITL__ENABLED` 默认 `false`；关闭时两个门控节点原样返回 `{}`，链路与接入前一致。

| 门控节点 | 触发条件 | 交互类型 |
| --- | --- | --- |
| `clarification_gate` | `requirement_validator` 判定 `workflow_status=clarification`（缺预算/用途等关键槽位） | `clarify_requirements` |
| `compatibility_gate` | `build_validator` 复核结果为 `SUCCESS` 且整体兼容性 `UNKNOWN` | `confirm_compatibility` |

以下情况**不中断**：兼容性为 `PASS` / `FAIL`；预算超限（Java 只返回 `WITHIN_BUDGET` / `NO_BUDGET`，`OVER_BUDGET` 不可达）。

```text
客户端 POST /api/v1/chat/stream（message）
  → requirement_parser → requirement_validator
  → clarification_gate（缺槽位时 interrupt）
  → SSE: interrupt（本轮结束，不发 done）
客户端 POST /api/v1/chat/stream（同 thread_id + resume{interrupt_id, answer}）
  → 校验 interrupt_id / TTL / 存储
  → 从 checkpoint 续跑：只重跑 clarification_gate
  → 合并补充信息 → requirement_parser → … → response_generator
  → SSE: token / done
```

- 恢复复用 `POST /api/v1/chat/stream`，不新增端点；请求体新增 `resume` 字段，与 `regenerate=true` 互斥（422 `validation_error`）。
- 兼容性门控选择 `abort` 时写入 `workflow_status=aborted`，`renderer` 输出固定终止文案，本轮正常 `done`。

## 12. HITL 载荷与恢复校验

```json
{
  "interrupt_id": "int-1",
  "interaction_type": "clarify_requirements",
  "question": "请补充预算和主要用途，我再为你推荐具体配置。",
  "input_schema": {
    "fields": [
      { "name": "budget_yuan", "label": "预算上限（元）", "type": "number", "required": true, "min": 1 },
      { "name": "scenario", "label": "主要用途", "type": "select", "required": false, "options": [{ "value": "GAMING", "label": "游戏" }] }
    ],
    "submit_label": "继续生成配置"
  },
  "context": { "missing_slots": ["budget_max_fen", "scenario"] },
  "schema_version": "1"
}
```

- `interrupt_id` 由 LangGraph 生成，客户端必须原样回传；服务端不自行编号。
- 字段 `type` 仅支持 `number` / `select` / `radio` / `text`；`options[].value` 必须来自固定枚举。
- 载荷只含用户可见信息，不带内部图状态、令牌或服务地址。

| 条件 | HTTP | code |
| --- | --- | --- |
| `HITL__ENABLED=false` 或 `STORAGE__BACKEND != postgres` | 409 | `hitl_unavailable` |
| `thread_id` 没有待恢复中断 | 409 | `interrupt_not_found` |
| `interrupt_id` 与当前中断不一致 | 409 | `interrupt_mismatch` |
| 距 checkpoint 创建超过 `HITL__INTERRUPT_TTL_SECONDS`（默认 1800） | 409 | `interrupt_expired` |
| `resume` 与 `regenerate` 同时出现 | 422 | `validation_error` |
| 回答缺少必填字段或取值非法 | 422（流内 `error` 事件） | `hitl_resume_invalid` |

## 13. HITL 历史与存储约束

- 提问文案在中断前由 `requirement_validator` / `build_validator` 追加 `AIMessage` 落库，恢复时历史里能看到本轮提问。
- 恢复时用户补充并入最后一条 `HumanMessage`（复用其 `id` 触发 `add_messages` 替换语义），不产生重复提问。
- 恢复回合以 `replace_existing=True` 覆盖写入本轮消息，避免 postgres `seq` 冲突与历史重复。
- 中断态不发送 `done`，前端把 `interrupt` 视为本轮终态（`awaiting_input`）；刷新历史后表单不会重建，需在本轮内完成回答。
- 中断依赖 LangGraph checkpointer，只有 `STORAGE__BACKEND=postgres` 会持久化；`memory` 后端进程重启即丢失，无法恢复。
- 配置层强制：`HITL__ENABLED=true` 且 `storage.backend != "postgres"` 时启动即 `ValueError`，不做静默降级；`hitl.py::_ensure_hitl_available` 运行期再兜底一次。
- 关闭时两个门控节点直接返回 `{}`，图结构虽新增节点，但路由与输出不变。

## 14. 一次请求时序

解析需求（LLM 或规则兜底）→ 校验 → 并发检索 8 类候选 → 补充 CPU/GPU 跑分与报价统计 → 求解（无解即结束）→ 校验（失败最多重解 1 次）→ 生成推荐说明并渲染 Markdown → 落库 `messages` → `done`（成功时附 `build_result`）。

> 相关决策见 [PC 配置模块决策合并记录](../adr/0027-pc-config-decisions.md)；阶段状态与遗留问题见 [roadmap](../planning/roadmap.md)。
