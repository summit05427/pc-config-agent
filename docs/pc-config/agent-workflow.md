# PC 配置 Agent 工作流

| 项 | 内容 |
| --- | --- |
| 状态 | 已验证（Stage 3 完成，Stage 5 联调通过） |
| 最后核验 | 2026-11-08 |
| 权威性 | 本文件描述 `app/agent/pc/graph.py` 与 `nodes.py` 的真实行为；SSE 契约以 [api-contract.md](../api-contract.md) §7 为准 |
| 主要证据 | `agent-service/app/agent/pc/graph.py`、`nodes.py`、`status.py`、`renderer.py`、`app/services/turn.py` |

## 1. 八个节点（含两个 HITL 门控）

| 节点 | 职责 | 输入 | 输出 | 失败分支 |
| --- | --- | --- | --- | --- |
| `requirement_parser` | 解析自然语言需求 | `messages`、`preference_prompt` | `requirements` | 模型失败 → 正则兜底；仍缺信息交给校验 |
| `requirement_validator` | 纯代码校验预算、场景与范围 | `requirements` | `validation_result` | `clarification` / `invalid` |
| `clarification_gate` | HITL：缺关键槽位时 `interrupt` 收集补充信息；关闭时直通 | `validation_result` | `messages`、`workflow_status` | 回答非法 → `hitl_resume_invalid` |
| `candidate_retriever` | 按 8 类并发检索候选、跑分与报价统计 | `requirements` | `candidate_pool` | `no_candidates` / `upstream_error` |
| `build_solver` | 调 Java 确定性求解 | `requirements`、`retry_count` | `build_result`、`build_failure`、`budget_report` | `no_solution` / `upstream_error` |
| `build_validator` | 调 Java 复核 8 类组合 | `build_result` | `compatibility_report` | `retry` / `compatibility_failed` |
| `compatibility_gate` | HITL：兼容性 `UNKNOWN` 时确认继续或终止；关闭时直通 | `compatibility_report` | `workflow_status` | 非法选择 → `hitl_resume_invalid` |
| `response_generator` | LLM 说明 + 代码渲染正文 | 全部业务字段 | `messages`、`reason_summary` | 非成功状态走确定性失败文案 |

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
- 门控节点无副作用，恢复时只重跑门控本身；完整时序与恢复校验见 [HITL 工作流](./hitl-workflow.md)。

## 3. 重解机制

- 校验失败且 `retry_count < AGENT__MAX_SOLVE_RETRIES`（代码默认 1）时返回 `retry`，条件边回到 `build_solver`。
- 重解时只放宽软偏好：`retry_count > 0` 时 `require_verified_offers` 固定为 `false`；预算与兼容性约束不变。
- 达到上限仍失败则返回 `compatibility_failed`，不继续循环。
- 该变量已收录于[环境变量文档](../deployment/environment-variables.md)（`AGENT__MAX_SOLVE_RETRIES`，默认 1）；同时写入 `agent-service/.env.example`，默认值以 `app/core/config.py` 为准。

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

## 6. 确定性兜底

- 非成功状态一律 `render_failure_markdown`，每个状态都有明确文案，不返回空串。
- 成功但模型不可用、返回空或文案含数字 / 型号 / 渠道时，改用 `_deterministic_reason`，正文仍由 `render_build_markdown` 渲染。
- 演示价存在时，正文首行与末尾都会插入「演示价格，非真实在售」声明。
- 兼容性 `UNKNOWN` 保留为「未验证」，不折算成通过。

## 7. 澄清判定

- `needs_clarification=true`，或预算为空且用户未明确用途 → `clarification`。
- 预算 `<= 0` → `clarification`，要求给出明确预算。
- 需求 Schema 校验失败 → `invalid`。
- 澄清只返回追问文本，不进入检索、求解，不产生 `build_result`。

## 8. 一次请求时序

解析需求（LLM 或规则兜底）→ 校验 → 并发检索 8 类候选 → 补充 CPU/GPU 跑分与报价统计 → 求解（无解即结束）→ 校验（失败最多重解 1 次）→ 生成推荐说明并渲染 Markdown → 落库 `messages` → `done`（成功时附 `build_result`）。
