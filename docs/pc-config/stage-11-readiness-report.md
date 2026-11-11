# Stage 11 基线审计与范围裁定

| 项 | 内容 |
| --- | --- |
| 状态 | 已审计（2026-11-09），本轮范围已裁定 |
| 权威性 | 本文件是 Stage 11 的能力基线、范围裁定与批次划分的唯一入口；任务书见 [Stage11.md](../planning/Stage11.md) |
| 审计方法 | 逐条对照当前分支源码与可执行配置，不采信历史报告；未在代码中出现的能力标为「缺失」 |
| 关联文档 | [agent-workflow.md](./agent-workflow.md)、[agent-state-and-tools.md](./agent-state-and-tools.md)、[testing-and-evaluation.md](./testing-and-evaluation.md)、[stage-10-readiness-report.md](./stage-10-readiness-report.md) |

## 1. 审计结论

| 子阶段 | 结论 | 依据摘要 |
| --- | --- | --- |
| 11.1 Evaluation / Observability / Guardrails / Context / Reliability | **大部分基础已存在**，缺口集中在「节点级追踪」「评估集规模」「输出层校验」 | 工具治理、上下文裁剪、Prometheus 指标、钩子系统均已落地 |
| 11.2 RAG | **本轮暂缓** | 无知识语料；RAG 仅有可插拔接缝，无 embedding、无向量库、无解析依赖 |
| 11.3 HITL | **完全缺失，但地基具备** | 全仓库无 `interrupt()` / `Command(resume=)`；持久化、线程隔离、幂等、会话锁、表单 UI 已具备 |
| 11.4 Memory | **结论可出**：暂缓独立记忆 | Java 已有用户偏好表，Agent 已按请求注入 `preference_prompt` |
| 11.5 MCP | **任务书前提失真**：已是 MCP 客户端 | `app/agent/mcp.py` + `mcp` / `langchain-mcp-adapters` 依赖已在 |
| 11.6 Multi-Agent | **结论可出**：`DEFERRED` | 确定性单图 + Java 求解器已覆盖，无拆分证据 |
| 11.7 集成验收 | **依赖 11.2 / 11.3** | RAG 暂缓后只能覆盖 HITL 与非 RAG 路径 |

**一句话结论**：Stage 11 可执行，但必须改写交付顺序；真正的新建工作只有「HITL 全链路」与「评估集扩容」，其余是收口与文档化。

## 2. 本轮范围裁定

| 子阶段 | 本轮处理 | 说明 |
| --- | --- | --- |
| 11.0 | **完成**（本文件） | 作为后续范围与验收依据 |
| 11.1 | 分项收口 | Guardrails / Context / Reliability 以补齐缺口为主；Evaluation 扩到可回归 |
| 11.2 RAG | **暂缓** | 语料获取是主成本，见 §4.4；重新评估条件见 §9 |
| 11.3 HITL | **必做** | 本轮唯一的大块新建能力 |
| 11.4 / 11.5 / 11.6 | 只出结论 | 各一份评估结论，不写代码 |
| 11.7 | 部分验收 | 只覆盖非 RAG 路径，RAG 相关条目挂起 |

**红线**：本阶段任何代码与测试不得读写、重置或覆盖 `offers.json` 与 Stage 9 采集产物。

## 3. 能力矩阵

图例：**已实现**＝代码可用且有测试；**有接缝**＝有接口与装配但无真实实现；**缺失**＝代码中不存在。

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| 六节点确定性图 + 条件路由 | 已实现 | [graph.py](../../agent-service/app/agent/pc/graph.py) L47-L154 |
| `PCConfigState` 字段与 reducer | 已实现 | [state.py](../../agent-service/app/agent/pc/state.py) L13-L33 |
| PostgreSQL Checkpointer | 已实现 | [checkpointer.py](../../agent-service/app/agent/checkpointer.py) L106-L151 |
| 工具治理（超时/重试/角色/限额/脱敏） | 已实现 | [registry.py](../../agent-service/app/agent/registry.py) L79-L93、L202-L272 |
| 上下文 token 裁剪与配对保护 | 已实现 | [context.py](../../agent-service/app/agent/context.py) L127-L155 |
| 请求幂等与会话级并发锁 | 已实现 | [idempotency.py](../../agent-service/app/services/idempotency.py)、[lock.py](../../agent-service/app/services/lock.py) |
| Prometheus 指标 + structlog | 已实现 | [metrics.py](../../agent-service/app/core/metrics.py) |
| 用户偏好注入 | 已实现 | [turn.py](../../agent-service/app/services/turn.py) L119-L136、Java `V5__create_user_preferences.sql` |
| 评估框架 | **有接缝** | [evals/schema.py](../../agent-service/evals/schema.py) L36-L70；用例仅 1 条 `example.yaml` |
| RAG 检索 | **有接缝** | [base.py](../../agent-service/app/rag/base.py) L14-L49；`RAG__ENABLED=false` |
| MCP 客户端 | 已实现（默认关闭） | [mcp.py](../../agent-service/app/agent/mcp.py) |
| citations 前端展示 | 已实现（2026-11-10） | [citations-list.tsx](../../frontend/src/features/chat/components/citations-list.tsx)：默认折叠、标题/片段/相关度，挂在助手消息正文之后；引用不落库，刷新后消失 |
| 节点级追踪 / trace 树 | 已实现 | [node_tracing.py](../../agent-service/app/agent/pc/node_tracing.py)、`agent_node_duration_seconds{node,status}` |
| HITL interrupt / resume | 已实现 | [hitl.py](../../agent-service/app/agent/pc/hitl.py)、[hitl-prompt.tsx](../../frontend/src/features/chat/components/hitl-prompt.tsx)，见 [hitl-workflow.md](hitl-workflow.md) |
| 输出层事实校验 | 已实现 | [output_guard.py](../../agent-service/app/agent/pc/output_guard.py) |
| 长期记忆 | **缺失（且本轮不建）** | — |

## 4. 逐端审计

### 4.1 Agent Service

- **图与节点**：六节点顺序固定，`requirement_parser` 与 `response_generator` 调用 LLM，其余为确定性节点；JSON 化 Markdown 由代码渲染，模型只产出说明文字，因此「编造型号」的风险面比自由生成小。
- **Java 调用**：`GET` 候选/跑分/报价/构建、`POST` 求解与校验；查询走服务令牌，求解与校验额外带 `X-User-Token`（[pc_client.py](../../agent-service/app/services/pc_client.py) L82-L125）。求解是**写操作**（会落快照），这是 HITL 重放的关键约束。
- **一次回合**：`run_turn` → 可选检索 → `astream` 翻译事件 → 先落库再发 `done`（[turn.py](../../agent-service/app/services/turn.py) L88-L150）。`done` 携带 `thread_id`，有 `build_result` 时才附带卡片数据。
- **SSE**：事件 ID、`schema_version`、TTFT、超时/断连处理集中在 [sse.py](../../agent-service/app/api/v1/sse.py) L34-L93。
- **线程隔离**：checkpoint 与 session 均按用户命名空间隔离（`namespaced_thread_id`），HITL 越权校验有现成基础。
- **缺口**：无节点耗时/节点级事件；无用户取消到 Graph 的显式信号；无输出事实校验；评估集只有骨架。

### 4.2 Frontend

- SSE 白名单仅 7 种事件：`token / reasoning / tool_call / tool_result / citations / done / error`（[sseStream.ts](../../frontend/src/core/http/sseStream.ts) L15-L28）。未知事件走默认分支忽略，新增事件不会破坏旧客户端。
- 回合状态机、取消（`abort`）、迟到事件过滤已实现（[agent-runtime.ts](../../frontend/src/features/chat/runtime/agent-runtime.ts)）。
- **HITL 的 UI 复用面充足**：组件库已注册 `Form / TextInput / NumberInput / Select / CheckboxGroup / RadioGroup / Button / ActionGroup`（[library/index.ts](../../frontend/src/features/generative-ui/library/index.ts)），动作白名单只有 `open_url` 与 `continue_conversation`，且 `continue_conversation` 已能提取表单值并作为新消息提交（[actions/index.ts](../../frontend/src/features/generative-ui/library/actions/index.ts) L69-L94、L150-L167）。

### 4.3 Java Application Service

- 内部接口清单：`/internal/v1/pc/hardware/candidates`、`/hardware/{id}`、`/benchmarks`、`/offers`；`/internal/v1/pc/builds/solve`、`/validate`、`/{buildId}`；`/internal/v1/auth/service-token`；`/internal/v1/model-tasks`（含 `{taskId}`、`credential-lease`）、`/model-access/check`、`/model-usage`。
- 用户偏好：`user_preferences`（`instructions / reply_language / response_style / use_history`）。
- 快照：`PcBuildInternalController` 的 `/{buildId}` 与 `V24__create_pc_build_snapshots.sql`。
- 结论：HITL 不需要 Java 新增接口；Java 侧除 P0-02 数据补齐外无改动。

### 4.4 数据与语料（RAG 暂缓的直接依据）

`f:\LLM_PC_Agent\Hardware data` 只有 PCPartPicker 结构化规格（8,238 条）与 PassMark 跑分（25,318 条），**不含任何官方 PDF、手册、CPU Support List、BIOS 说明或内存 QVL**。Stage 11 §5.1 的 10 类知识范围无一份现成语料，且 §5.4 的表格感知切块需要版面解析或人工标注。在语料与解析策略确定前实施检索器，只能得到无法验收的空壳。

## 5. 与任务书不一致的既成事实

1. **MCP 已采用为客户端**：任务书 §8 按「尚未引入」描述，实际已有经 LiteLLM 网关的 MCP 客户端与依赖。真实待决问题是「是否对外暴露 MCP Server」与「存量客户端是否保留」。
2. **HITL 不是「扩展现有契约」而是新建契约**：前端无 interrupt 类事件，Agent 无 resume 入参；任务书「优先扩展现有契约」只能理解为「复用同一流式端点与同一套消息结构」，而不是「已有事件可直接用」。
3. **citations 展示能力已于 2026-11-10 补齐**：任务书 §5.8 要求「复用现有 citations SSE 事件和前端展示能力」——审计时事件与类型解析存在、展示组件不存在；现由 `citations-list.tsx` 承接，运行时按 `sourceId` 去重后挂在当前助手消息上。
4. **`docs/services/agent-service/architecture.md` 已过期**：其「无 RAG/向量检索、无 MCP 工具接入」的表述与代码矛盾，应在下一批修正。

## 6. 契约影响（HITL）

| 变更 | 范围 | 说明 |
| --- | --- | --- |
| 新增 SSE 事件（暂名 `interrupt`） | Agent `sse.py` + 前端白名单与运行时 + [docs/api-contract.md](../api-contract.md) §7 | 载荷需含 `interrupt_id`、`interaction_type`、`question`、`input_schema` 或选项、上下文摘要、状态；**不得**暴露内部 Graph State |
| 恢复入口 | 复用 `POST /api/v1/chat/stream` 增加恢复语义字段，或新增同族端点 | 二选一，需在实施前定稿；两种都必须复用同一 `thread_id` |
| citations 扩展 | Agent `Citation` + 前端 `ChatCitation` + 契约文档 | 本阶段暂缓，RAG 恢复时补页码/章节/版本/来源链接 |
| 错误码 | `error_codes.py` + 契约错误码表 | 新增「中断已过期」「重复恢复」「恢复不匹配」 |

Java DTO 不受影响。

## 7. 可直接复用（禁止重写）

- Checkpointer 装配、连接池、就绪探测：直接承载 HITL 持久化。
- 用户命名空间化 thread id 与 `session_meta(user_id, thread_id)` 主键：直接作为 HITL 权限校验。
- `Idempotency-Key` 与线程锁：直接作为「重复恢复不重复执行」的第一道防线。
- ToolSpec 治理链：新增工具必须登记，不得另建权限体系。
- OpenUI 表单 + `continue_conversation`：作为 HITL 输入界面，不新做确认页。
- 评估框架的 YAML 加载与 fake/real 双 runner：只扩 schema 与用例集。

## 8. 批次与前置条件

| 批次 | 内容 | 前置 | 验收 |
| --- | --- | --- | --- |
| 批 1 | 本文档 + 11.1 收口（节点级追踪、评估集扩容、输出事实校验）+ 11.4/11.5/11.6 结论 | 无 | ruff / mypy / pytest / evals 全绿；文档索引登记 |
| 批 2 | 11.3 HITL 全链路（契约、节点幂等、SSE、前端表单、权限与过期、恢复测试） | 批 1 的契约变更流程 | 11 条 HITL 验收用例全绿；无中断流程零回归 |
| 批 3 | 11.2 RAG（语料准备 → 解析与切块 → pgvector → 检索器 → 引用 UI） | 语料来源与合法性确认 | 另立阶段任务书 |

## 9. 未决事项与重新评估条件

| 编号 | 事项 | 影响 | 建议 |
| --- | --- | --- | --- |
| U-01 | HITL 恢复入口：复用 `/chat/stream` 带恢复字段，还是新增同族端点 | 契约与前端改动量 | 复用同一端点，恢复语义显式化 |
| U-02 | HITL 在 `STORAGE__BACKEND=memory` 下的行为 | 本地开发与 Solo 体验 | 拒绝中断并明确报错，不静默降级 |
| U-03 | 评估是否允许在 CI 调用真实模型 | 成本、凭证与稳定性 | CI 只跑 fake；真实模型本地手动并按基线对比 |
| U-04 | 新增依赖（embedding 通道、PDF 解析、向量客户端） | 供应链与运维 | RAG 恢复前单独审批 |
| U-05 | RAG 重新评估条件 | 阶段启动门槛 | 至少具备 3 类官方语料的合法来源与解析方案 |

## 10. 下一步

批 1、批 2 已完成；批 3（11.2 RAG）按决策暂缓，恢复条件见 U-05。11.7 集成验收的 RAG 之外部分已完成，记录见附录 D。

## 附录 A：Stage 11.4 Memory 结论

| 能力 | 定位 | 现状 |
| --- | --- | --- |
| Checkpointer | 单会话执行状态 | 已实现，按用户命名空间隔离 |
| 用户偏好 | 跨会话的显式偏好 | Java `user_preferences` 持有，Agent 每轮按请求注入 |
| BuildSnapshot | 历史配置与当时数据 | Java 持有，Agent 只读 |
| 长期记忆 | 自动提炼的偏好与事实 | **不建设** |

**结论**：本轮不引入独立的长期记忆存储。

1. 现有偏好由 Java 作为权威存储，Agent 只是消费者；再建一套记忆库会产生第二个用户资料权威，违反既定边界。
2. 历史配置已有 BuildSnapshot，不需要用记忆替代。
3. 当前没有「自动提炼偏好并跨会话复用」的产品需求证据；无授权模型与用户可查看/删除界面时，自动记忆不可上线。

**重新评估条件**：出现明确的跨会话个性化需求，且 Java 侧提供偏好写入 API 与用户可见的偏好管理界面；届时记忆只能作为偏好数据的派生视图，不得反向成为权威。

## 附录 B：Stage 11.6 Multi-Agent 结论

**结论：`DEFERRED`，本轮不引入。**

- 现有核心流程是确定性单图 + Java 全局求解器；硬件组合属于全局约束优化，拆分给多个局部 Agent 会直接破坏求解完整性。
- 三个候选场景（复杂技术研究、升级研究、多知识源并行）都缺少真实需求与可量化收益；在 RAG 语料尚不存在时，多知识源并行更没有对象。
- 成本项明确：模型调用次数与 Token 成倍增加、跨 Agent 状态与冲突合并、调试与追踪复杂度上升、端到端延迟增加。

**重新评估条件**：单图出现可测量的并行收益（例如多份官方文档研究可并行且端到端延迟显著下降），并有固定测试证明质量不降；即便如此，最终整机配置仍必须由 Java BuildSolver 产出。

## 附录 C：批 1 交付记录（2026-11-09）

| 子项 | 交付 | 证据 | 校验 |
| --- | --- | --- | --- |
| 1-A 评估扩容 | `evals/schema.py` 新增 `workflow_status` / `tool_sequence` / `missing_slots` / `structured_fields` / `price_consistency` / `max_latency_ms` / `max_tokens` 与多轮 `turns`；新增十类场景用例 | `agent-service/evals/cases/pc-config-scenarios.yaml`、`tests/test_evals.py` | `python -m evals --fake` 14 条用例、0 失败；`pytest` 544 例、92.34% |
| 1-B 节点级追踪 | 六节点统一包装，新增 `agent_node_duration_seconds{node,status}` 与 `agent.node.completed` 事件 | `agent-service/app/agent/pc/node_tracing.py`、`app/agent/pc/graph.py`、`tests/test_node_tracing.py` | 同步与 async 节点均有覆盖；异常路径原样抛出 |
| 1-C 输出事实校验 | 价格/预算自洽、未验证项不得宣称已确认（含否定语境）、模型文案越界检查；命中即降级为确定性说明并追加可见提示 | `agent-service/app/agent/pc/output_guard.py`、`app/agent/pc/nodes.py`、`tests/test_output_guard.py` | `agent_output_guard_violations_total{rule}` 指标可采集 |

**未改变的事实**：RAG 仍暂缓；HITL 仍需批 2；`docs/services/agent-service/architecture.md` 的 RAG/MCP 表述已按审计结论修正。

## 附录 D：批 2 与 11.7 验收记录（2026-11-10）

### D.1 批 2：11.3 HITL 全链路

| 子项 | 交付 | 证据 |
| --- | --- | --- |
| 配置与启动校验 | `HitlSettings`（默认关闭、TTL 1800s）；`HITL__ENABLED=true` 且非 postgres 时启动失败 | `app/core/config.py`、`tests/test_hitl.py` |
| 图与门控 | 新增 `clarification_gate` / `compatibility_gate`，八节点；门控无副作用且位于写操作之后 | `app/agent/pc/hitl.py`、`graph.py`、`app/agent/pc/status.py` |
| 回合与恢复 | SSE 新增 `interrupt`（8 类事件）；`POST /chat/stream` 新增 `resume{interrupt_id, answer}`；5 类恢复错误码 | `app/services/turn.py`、`app/api/v1/chat.py`、`docs/api-contract.md` §7 |
| 前端表单 | 按 `input_schema.fields` 渲染 number/select/radio/text；提交带 `resume` 续跑，中断态 `awaiting_input` | `frontend/src/features/chat/components/hitl-prompt.tsx`、`agent-runtime.ts` |
| 历史与持久化 | 提问由校验节点落库；恢复复用用户消息 id 合并补充，并以 `replace_existing=True` 重写本轮 | `app/agent/pc/nodes.py`、`app/services/turn.py` |

### D.2 11.7 集成验收（剔除 RAG）

| 任务书小节 | 验收项 | 结果 | 证据 |
| --- | --- | --- | --- |
| 10.2 HITL + Agent | 暂停、恢复、终止；重建图后仍可恢复 | 通过 | `tests/test_hitl.py`（含 `test_interrupt_survives_graph_rebuild`） |
| 10.3 Evaluation | 固定评估集含 HITL 场景；fake 模式零费用可加载 | 通过 | `evals/cases/pc-config-scenarios.yaml` 15 条、`--fake` 0 失败；real runner 支持 `resume` 与 `interrupt_type` 断言 |
| 10.4 Guardrails | Prompt Injection、无效工具参数、越权、重复调用、越界数字、非法恢复请求 | 通过 | `tests/test_output_guard.py`、`tests/test_tool_governance.py`、`tests/test_hitl.py`（5 类恢复错误码） |
| 10.5 整体回归 | 前端流式、BuildResult、OpenUI、无 HITL 请求；后端全量 | 通过 | 后端 562 例 / 92.30%；前端 500 例 / 92.32%；ruff、mypy、evals、文档链接全绿 |
| 10.1 RAG + Agent | 语料、切块、pgvector、引用 UI | **未验收（按决策暂缓）** | 恢复条件见 U-05 |

**结论**：Stage 11.7 在 RAG 之外达到任务书验收要求；RAG 相关项不计入本次验收，不得对外宣称已具备知识库检索能力。



