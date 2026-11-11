# Stage 11 批 2：HITL 全链路实施计划

## Context

Stage 11 批 1 已交付（评估扩容、节点追踪、输出校验，544 用例 / 92.34%）。批 2 目标是补齐 HITL（Human-in-the-Loop）全链路：当 PC 配置流水线缺少关键槽位或兼容性无法确认时，图暂停并向用户提问；用户回答后从断点恢复，而不是丢掉上下文重新提问。

已由用户确认的两项决策：

- **U-01**：恢复入口复用 `POST /api/v1/chat/stream`，通过新增请求字段携带恢复信息，不新增端点。
- **U-02**：`STORAGE__BACKEND=memory` 时拒绝中断并明确报错，不静默降级。
- **补充决策（本轮确认）**：新增 `HITL__ENABLED` 开关，默认 `false`，保证现有澄清/构建流程零回归；显式开启且后端为 memory 时启动即报错。

红线：任何代码与测试不得读写、重置或覆盖 `offers.json` 与 Stage 9 采集产物。

## 设计要点

### 1. 图结构：门控节点放在写操作之后，恢复不重放写操作

LangGraph 的 `interrupt()` 恢复时只重跑**中断所在节点**，已完成节点的状态来自 checkpoint。因此：

- 澄清门控放在 `requirement_validator` 之后、`candidate_retriever` 之前；
- 兼容性门控放在 `build_validator` 之后、`response_generator` 之前。

`build_solver` / `build_validator` 已提交的状态不会被重跑，避免 Java 求解重复落快照。门控节点本身只读写图状态，无 I/O，可安全重放。

新增路由：

```text
requirement_parser -> requirement_validator
requirement_validator --clarification--> clarification_gate
requirement_validator --其它--> candidate_retriever -> build_solver -> build_validator
build_validator --retry--> build_solver
build_validator --success + 兼容性 UNKNOWN--> compatibility_gate
build_validator --其它--> response_generator
clarification_gate --仍为 clarification（未启用）--> response_generator
clarification_gate --已恢复--> requirement_parser
compatibility_gate --> response_generator
```

### 2. 中断载荷契约（只暴露用户可见信息）

```json
{
  "interrupt_id": "…",
  "interaction_type": "clarify_requirements | confirm_compatibility",
  "question": "…",
  "input_schema": { "fields": [ { "name", "label", "type", "required", "options" } ] },
  "context": { "missing_slots": [...], "unverified_rules": [...] },
  "schema_version": "1"
}
```

禁止把内部 Graph State、令牌、内部地址放进载荷。

### 3. 恢复校验（流建立前，失败返回裸 JSON）

- 未开启 HITL 或 `STORAGE__BACKEND=memory` → `409 hitl_unavailable`；
- 该 thread 无 pending interrupt → `409 interrupt_not_found`；
- `interrupt_id` 不匹配 → `409 interrupt_mismatch`；
- 距 checkpoint 创建超过 `HITL__INTERRUPT_TTL_SECONDS` → `409 interrupt_expired`；
- `resume` 与 `regenerate` 同时出现 → `422`。

跨用户/跨 thread 由 `namespaced_thread_id` + 按 thread 读取 checkpoint 天然拒绝。

### 4. 历史回显

- 澄清问题由 `requirement_validator` 在返回时追加一条 `AIMessage`（仅 HITL 开启且为 clarification）；
- 兼容性问题由 `build_validator` 在返回时追加一条 `AIMessage`（仅 HITL 开启且 overall=UNKNOWN）；
- 中断时先 `_persist_turn` 再结束，历史可见问题；
- 恢复完成后用 `replace_existing=True` 重写本轮消息，使用户补充内容进入同一条用户消息。

### 5. memory 模式

配置层 fail-fast：`HITL__ENABLED=true` 且 `STORAGE__BACKEND != "postgres"` → 启动报错。运行期恢复入口再做一次 `hitl_unavailable` 防御。

## 后端改动

| 文件 | 改动 |
| --- | --- |
| `agent-service/app/core/config.py` | 新增 `HitlSettings(enabled=False, interrupt_ttl_seconds=1800)`；注册 `hitl`；`model_validator` 校验 enabled 必须配 postgres |
| `agent-service/app/core/error_codes.py` | 新增 `hitl_unavailable`、`interrupt_not_found`、`interrupt_expired`、`interrupt_mismatch`、`hitl_resume_invalid` |
| `agent-service/app/core/exceptions.py` | 新增 `HitlResumeInvalidError(AppError, 422)` |
| `agent-service/app/agent/pc/status.py` | 新增 `STATUS_ABORTED = "aborted"` |
| `agent-service/app/agent/pc/renderer.py` | `render_failure_markdown` 增加 aborted 分支 |
| `agent-service/app/agent/pc/hitl.py`（新建） | 交互常量、字段 schema、`clarification_gate`、`compatibility_gate`、答案合并与校验 |
| `agent-service/app/agent/pc/nodes.py` | 澄清/兼容性分支按 `hitl.enabled` 追加问题 `AIMessage`；关闭时行为不变 |
| `agent-service/app/agent/pc/graph.py` | 注册两个门控节点与四条新路由；扩展 `PC_GRAPH_NODES` |
| `agent-service/app/agent/pc/node_tracing.py` | 中断异常记为 `interrupted`，不计为 error |
| `agent-service/app/services/turn.py` | `TurnEventType` 加 `interrupt`；`TurnRequest.resume`；`TurnOutcome.interrupted`；检测 `__interrupt__` 并翻译；中断时不发 `done`；恢复时传 `Command(resume=...)` 且 `replace_existing=True` |
| `agent-service/app/api/v1/chat.py` | `ChatResume` 与 `ChatRequest.resume`；流建立前 `_validate_resume`；`_event_stream` 捕获 `AppError` 输出明确错误码 |
| `agent-service/app/api/v1/sse.py` | 按需补一个 `AppError` 编码方法（复用现有 `encode` 格式） |

## 前端改动

| 文件 | 改动 |
| --- | --- |
| `frontend/src/core/http/sseStream.ts` | 事件白名单加入 `interrupt` |
| `frontend/src/features/sessions/api/types.ts` | `ChatStreamEvent` 增 `interrupt`；请求体增 `resume`；新增 `HitlPrompt` 类型；运行状态增 `awaiting_input` |
| `frontend/src/features/sessions/api/stream-chat.ts` | 解析 `interrupt` 为类型化事件 |
| `frontend/src/features/chat/runtime/types.ts` | 消息附加 `hitl` 提示；状态增 `awaiting_input` |
| `frontend/src/features/chat/runtime/agent-runtime.ts` | `interrupt` 作为本轮终态（不判失败）；保存 prompt；新增 `resume(answerText, answer)` |
| `frontend/src/features/chat/hooks/use-agent-runtime.ts` | 暴露 `resumeHitl` |
| `frontend/src/features/chat/components/hitl-prompt.tsx`（新建） | 按 `input_schema` 渲染字段；提交 `{ message, resume: { interrupt_id, answer } }` |
| `frontend/src/features/chat/components/message-content.tsx` | 状态为 `awaiting_input` 且带 `hitl` 时渲染 `HitlPrompt` |

## 测试

- `agent-service/tests/test_hitl.py`（新建）：配置 fail-fast；门控在关闭时透传；clarification 中断→恢复后重新解析；空回答报 `hitl_resume_invalid`；兼容性 UNKNOWN 选择 abort 后状态为 `aborted`。
- `agent-service/tests/test_agent_graph.py`：把「恰好六节点」断言改为包含门控节点；验证关闭 HITL 时原澄清流程零回归。
- `agent-service/tests/test_chat_stream.py`（或现有对话测试）：恢复校验五个错误码。
- 前端：`stream-chat` 与 `agent-runtime` 的 interrupt 处理单测。

## 文档与环境变量

- `.env.example`：`HITL__ENABLED=false`、`HITL__INTERRUPT_TTL_SECONDS=1800`。
- `docs/deployment/environment-variables.md`：新增两项说明。
- `docs/api-contract.md` §7：请求字段 `resume`、SSE `interrupt` 事件、五个错误码。
- `docs/pc-config/hitl-workflow.md`（新建）：触发条件、时序、恢复校验、memory 限制。
- `docs/pc-config/README.md`、`docs/INDEX.md` 登记。
- `docs/services/agent-service/agent-workflows.md`、`api-reference.md`、`agent-service/CODEMAP.md` 同步落点。

## 验证

```powershell
uv --directory agent-service run ruff check app tests evals run.py
uv --directory agent-service run mypy
uv --directory agent-service run pytest -q --cov=app --cov-report=term-missing
uv --directory agent-service run python -m evals --fake

corepack pnpm --dir frontend lint:ci
corepack pnpm --dir frontend type-check
corepack pnpm --dir frontend test:coverage

powershell -File scripts/check-doc-links.ps1
```

真实模型用例（`evals --real`）与四端联调不在本轮 CI 范围，按需本地手动执行。

## 不在本轮范围

- RAG 语料接入与 citations UI（批 3，暂缓）。
- 超预算门控：Java 求解只返回 `WITHIN_BUDGET` / `NO_BUDGET`，`OVER_BUDGET` 不可达，不臆造。
- 长期记忆、Multi-Agent（维持 `DEFERRED`）。
