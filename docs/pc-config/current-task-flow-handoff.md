# PC 配置任务全流程交接说明

| 项 | 内容 |
| --- | --- |
| 用途 | 供后续 Agent 制定「LLM 选型 + 多 Agent + RAG」重构计划时，快速掌握当前一次任务的完整处理过程、代码分层、可用工具与约束 |
| 状态 | 现状快照（2026-11-13），对应「推荐质量与模型降级整改」落地后的代码 |
| 读者 | 只需要读这一份即可开始规划；细节以本文列出的源码为准 |
| 不包含 | 重构方案本身、未实施设想、历史缺陷的完整复盘（见 `recommendation-quality-remediation.md`） |

## 0. 一句话现状

**LLM 只做两件事：把自然语言解析成结构化需求、把已确定的方案写成 2–3 句说明；硬件候选、筛选、评分、兼容性校验、最终组合全部由 Java `BuildSolver` 确定性完成。** Agent 侧只负责编排、工具调用、质量评审与渲染，不参与选型决策。

## 1. 拓扑与运行入口

| 组件 | 本地端口 | 职责 |
| --- | --- | --- |
| `frontend/`（React 19 + Vite） | 5273 | 对话、需求向导、SSE 渲染、结果卡片 |
| `admin/` | 5274 | 管理端，与本流程无直接关系 |
| `application-service/`（Java 21） | 18080（`.env` 的 `BACKEND_PORT`） | JWT 签发、硬件目录、报价/跑分、确定性求解与兼容校验、快照落库 |
| `agent-service/`（Python 3.12 + LangGraph） | 18000（`AGENT_PORT`） | 需求解析、图编排、工具治理、质量评审、正文渲染、会话落库 |
| LiteLLM | 容器内 `litellm:4000` | 统一模型网关（平台托管模型 + BYOK） |
| PostgreSQL / pgvector / Redis | 容器 | Java 库 `agent`；Agent 库 `agent_service`；Redis 用于限流等旁路能力 |

调用方向固定：浏览器 → Agent（`/api/v1/chat/stream`）→ Java 内网接口（`/internal/v1/pc/**`）。Java 不调用 Agent。

## 2. 一次任务的端到端时序

1. **前端发起**：`POST /api/v1/chat/stream`，请求体含 `message`、`thread_id`、可选 `agent_id` / `model` / `preferences` / `resume` / `regenerate`。
2. **鉴权**：Agent 校验 Java 签发的 RS256 JWT（issuer、audience、`token_use=access`、`kid`），得到 `user_id` 与 `roles`。
3. **模型解析**：`model_resolver.resolve_runtime`。显式模型 → 校验会话选择；Auto → 调 Java 控制面（`/internal/v1/model-runtime/**`）解析；BYOK 走凭据租约。控制面不可达时当前实现直接报错，不再退回平台默认模型（整改 P0-2）。
4. **RAG（可选，默认关闭）**：`RAG__ENABLED=true` 时按 `user_id`/`roles` 先过滤再检索，产出 `citations` 事件，并把片段拼进本轮提示词；检索失败按「无引用」降级。
5. **进入图**：`turn.py::run_turn` 用 `graph.astream(..., stream_mode=["messages","updates","custom"])` 驱动 9 节点流水线。
6. **需求解析**：`requirement_parser` 调 LLM（`TAG_NOSTREAM`，只输出 JSON）得到 `PCRequirements`；模型不可用时走正则兜底 `fallback_requirements`。
7. **需求校验**：`requirement_validator` 纯代码判断预算、场景、区间与缺失槽位，产出 `clarification` / `invalid` / 继续。
8. **澄清门控**：`clarification_gate` 在 HITL 开启时 `interrupt` 等待用户补充；关闭时原样放行，直接给澄清文案。
9. **候选检索**：`candidate_retriever` 并发查 8 类候选（只取 `total` 与 `catalogVersion`）、CPU/GPU 跑分、报价统计，共 11 次工具调用；缺任一类别即 `no_candidates`。成功路径全链路累计 13 次（再加求解与校验）。
10. **确定性求解**：`build_solver` → `solve_pc_build` → Java `POST /internal/v1/pc/builds/solve`。Java 负责建池、搜索、评分、兼容剪枝，并写入 `pc_build_snapshots`（append-only），返回 `buildId`、8 类组件、总价、兼容报告、逐件理由。
11. **兼容复核**：`build_validator` → `validate_pc_build` → Java `POST /internal/v1/pc/builds/validate`。失败且 `retry_count < AGENT__MAX_SOLVE_RETRIES`（默认 1，上限 2）时回到求解，重解只放宽软偏好（`require_verified_offers=false`），不放宽预算与硬兼容。
12. **质量评审**：`quality_review` 用确定性规则检查 CPU/GPU 价格失衡、办公/影音显卡超支、总价低于预算下限；可修正时带 `minCpuPriceFen` / `maxGpuPriceFen` 重解至多 1 次，否则生成 `quality_notice`。
13. **兼容门控**：整体结论为 `UNKNOWN` 且 HITL 开启时 `interrupt` 让用户确认；`abort` 写入 `aborted`。
14. **生成回复**：`response_generator` 先让 LLM 生成 2–3 句说明（禁止数字、型号、品牌、链接），再用确定性渲染器拼出推荐清单、总价、兼容性结论；思考内容经 `custom` 流逐片下发，正文在校验后分块下发。
15. **落库**：`turn.py` 先 `session_store.record_turn` 写 `session_messages` / `session_meta`（含 `build_result`），再发 `done`。
16. **前端渲染**：`reasoning` → 思考面板；`tool_call` / `tool_result` → 阶段文案；`token` → 正文；`done.build_result` → 结果卡片；`interrupt` → HITL 表单。

## 3. 九个图节点

| 节点 | 实现 | 输入 | 输出 | 失败/分支 |
| --- | --- | --- | --- | --- |
| `requirement_parser` | `app/agent/pc/nodes.py` | `messages`、`preference_prompt` | `requirements` | LLM 失败 → 正则兜底；每轮清零质量字段 |
| `requirement_validator` | 同上 | `requirements` | `validation_result`、`workflow_status` | `clarification` / `invalid` |
| `clarification_gate` | `app/agent/pc/hitl.py` | `validation_result` | `messages`、`workflow_status` | 回答非法 → `hitl_resume_invalid` |
| `candidate_retriever` | `nodes.py` | `requirements` | `candidate_pool`（8 类计数、跑分、报价统计） | `no_candidates` / `upstream_error` |
| `build_solver` | `nodes.py` + `pc/tools.py` | `requirements`、`retry_count`、`quality_constraints` | `build_result`、`build_failure`、`budget_report` | `no_solution` / `upstream_error` |
| `build_validator` | `nodes.py` | `build_result` | `compatibility_report` | `retry` / `compatibility_failed` |
| `quality_review` | `app/agent/pc/quality.py` | `requirements`、`build_result` | `quality_review`、`quality_notice`、`quality_constraints` | 可修正 → `retry`（≤1 次） |
| `compatibility_gate` | `hitl.py` | `compatibility_report` | `workflow_status` | 非法选择 → `hitl_resume_invalid` |
| `response_generator` | `nodes.py` + `pc/renderer.py` | 全部业务字段 | `messages`、`reason_summary` | 非成功状态走确定性失败文案 |

路由只读 `workflow_status`，状态常量在 `app/agent/pc/status.py`。完整路由图见 `docs/pc-config/agent.md` §2。

**关键事实：`candidate_retriever` 不把候选清单放进状态**，只保留各类别数量、CPU/GPU 最高跑分与报价统计。LLM 在任何节点都看不到具体硬件条目，也不可能参与选型。

## 4. 状态与持久化

`PCConfigState`（`app/agent/pc/state.py`）字段：

- 契约字段：`messages`、`preference_prompt`、`use_history`；
- 业务字段：`requirements`、`validation_result`、`candidate_pool`、`build_result`、`build_failure`、`compatibility_report`、`budget_report`、`reason_summary`、`retry_count`、`workflow_status`；
- 质量字段：`quality_review`、`quality_notice`、`quality_constraints`、`quality_retry_count`；
- 进度字段：`tool_events`（列表拼接归约，由 `turn.py` 翻译成 SSE）。

持久化分工：

| 数据 | 位置 | 说明 |
| --- | --- | --- |
| 图检查点 | `checkpointer`（默认 `MemorySaver`；`STORAGE__BACKEND=postgres` 时 `AsyncPostgresSaver`） | 只用于单轮内恢复与 HITL 续跑 |
| 会话消息与标题 | `agent_service.session_messages` / `session_meta` | 历史接口只读这里，不读检查点 |
| 方案快照 | Java `agent.pc_build_snapshots` | `solve` 时写入，append-only，含需求快照与报价快照 |
| 反馈 | Java `message_feedback` | 按 Agent 下发的 `{thread_id}:{seq}` 绑定，不存正文 |

## 5. Agent 可用工具（运行时）

全部通过 `@register_tool` 注册，节点只能用 `get_governed_tool(name)` 取用，禁止直接 `httpx`。

| 工具 | 参数 | 上游 | 超时 | 输出上限 | 单轮配额 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| `search_hardware_candidates` | `category?` | `GET /internal/v1/pc/hardware/candidates` | 10s | 4000 | 12 | 返回 `total`、`list`、`catalogVersion` |
| `get_benchmark_data` | `hardware_id?`、`category?` | `GET /internal/v1/pc/benchmarks` | 10s | 4000 | 12 | 无数据返回空，不猜测 |
| `get_verified_offers` | `hardware_id?`、`category?`、`verified_only=false` | `GET /internal/v1/pc/offers` | 10s | 6000 | 12 | 可能含 `MOCK_DEMO`，必须标注 |
| `solve_pc_build` | `budget_min_fen?`、`budget_max_fen?`、`scenario`、`preference?`、`render_mode?`、`min_memory_gb?`、`min_storage_gb?`、`require_verified_offers`、`min_cpu_price_fen?`、`max_gpu_price_fen?` | `POST /internal/v1/pc/builds/solve` | 60s | 8000 | 3 | `is_read_only=false`，必须带 `X-User-Token` |
| `validate_pc_build` | 8 类组件 ID（均必填） | `POST /internal/v1/pc/builds/validate` | 10s | 4000 | 3 | 只校验，不选型 |

治理机制（`app/agent/registry.py`）：

- 输出先转文本，按 `AGENT__TOOL_REDACT_OUTPUT=true` 脱敏手机号、邮箱、身份证、API Key、Bearer，再按 token 预算截断；
- 配额用 `ToolTurn` 的 `ContextVar` 累计，超限返回提示文本而非抛错；
- 上游异常统一包成 `ToolExecutionError`，内部地址与堆栈只进日志；
- 重试统一取 `AGENT__TOOL_MAX_RETRIES`（默认 1）。

Java 内网接口鉴权：服务令牌 `token_use=service`，用户维度额外带 `X-User-Token`；`solve` / `get build` 类接口缺用户身份直接拒绝。

## 6. Java 求解器现状（重构的核心对象）

入口：`application-service/.../pcbuild/application/BuildSolveService.java` → `BuildSolver.solve(...)`。

### 6.1 输入模型

`BuildRequirements` 字段：`budgetMaxFen`、`budgetMinFen`、`minCpuPriceFen`、`maxGpuPriceFen`、`scenario`、`minMemoryGb`、`minStorageGb`、`requireVerifiedOffers`、`workloadProfile`、`renderMode`、`scoringVersion`、`preference`。

语义：

- `budgetMaxFen` 是硬约束；`budgetMinFen` 只用于校验与文案，不强制多花钱；
- `scenario` 决定 CPU/GPU 权重：`GAMING 30/70`、`CREATIVE 55/45`、`PROGRAMMING 80/20`、`WORKSTATION 60/40`、`OFFICE 85/15`、`MEDIA 70/30`、`BALANCED 50/50`、`AI_INFERENCE 40/60`；
- `workloadProfile` 决定候选排序策略与评分细则；`RENDERING` 会按 `renderMode` 重新推导场景；
- `preference=VALUE` 时有预算也按「总分×1,000,000/价格」排序，否则按总分优先、价格次之。

### 6.2 候选池构建

1. `cheapestUsableOffers`：每个硬件取一条可用报价，按 `pricingDate` 与 `requireVerifiedOffers` 过滤；
2. `collectRawPools`：过滤不可求解、容量不达标、无报价的条目；有预算时剔除单件超预算候选（全超时保留，交给上层报 `BUDGET_EXCEEDED`）；
3. `buildCompatiblePools`：
   - CPU/GPU：性能前 8 + 最低价 4 + 按价格分桶补足（桶上界 1000/2000/4000/8000 元，每桶 ≤2），总上限约 22；
   - MEMORY：按 `memory_type` 分组，每组 8；
   - MOTHERBOARD：按 `(socket, memoryType)` 分组，每组 6；
   - 其他类别：按画像排序取前 8；
   - 组装顺序上先按 CPU socket、内存类型、主板板型、显卡限长、散热器插槽做兼容过滤，再截断；
   - 质量约束 `minCpuPriceFen` / `maxGpuPriceFen` 在此处裁剪；整类被筛空时退回原候选。

### 6.3 搜索与评分

- 搜索顺序固定：CPU → MOTHERBOARD → MEMORY → GPU → PSU → CASE → COOLER → STORAGE；
- 增量剪枝：加入主板查 socket、加入内存查类型与插槽数、加入 PSU 查功率、加入机箱查板型与显卡长度；完成时再跑全部 9 条规则；
- 预算剪枝：累计价格已超上限即回溯；
- 有预算但无解时，用「去掉预算」的独立探针搜索求最低可行总价，只返回该金额，绝不返回超预算方案；
- 评分：`BuildScoring.totalScore` 按场景权重合成 CPU/GPU 分，叠加内存容量、存储容量、显存加成；所有整数运算，平局按价格、再按 `hardwareId` 保证确定性。

### 6.4 兼容性规则（9 条，全部 BLOCKING）

`cpu_socket_motherboard`、`motherboard_memory_type`、`motherboard_case_form_factor`、`gpu_case_length`、`cooler_cpu_socket`、`cooler_case_height`、`gpu_psu_power`、`storage_motherboard_m2`、`memory_module_count`。

字段缺失返回 `UNKNOWN`，不得折算成 `PASS`；`UNKNOWN` 会触发 HITL 兼容性确认（HITL 开启时）。

## 7. 数据源

| 数据 | 位置 | 规模/说明 |
| --- | --- | --- |
| 硬件目录 | `application-service/src/main/resources/pc-config/catalog.json` | 约 640KB，8 类数百条，含 socket、内存类型、板型、限长、TDP 等规格 |
| 报价 | `.../pc-config/offers.json` | 约 280KB，含 `priceSource`（`OWNER_VERIFIED` / `MOCK_DEMO`）与核验时间 |
| 跑分 | `.../pc-config/benchmarks.json` | 约 78KB，CPUMARK / G3D_MARK / 单线程分 / 显存等 |

数据加载在 Java 启动期完成（`Json*Repository`），求解不实时查库；快照落库用于回溯与结果卡片。

## 8. SSE 事件与前端渲染

| SSE 事件 | 生产者 | 前端行为 |
| --- | --- | --- |
| `citations` | `turn.py`（RAG 开启） | 引用区 |
| `reasoning` | `messages` 流的 `reasoning_content`，或节点 `custom{kind:"reasoning"}` | 思考面板逐字追加，先于正文 |
| `tool_call` / `tool_result` | 节点 `tool_events` 经 `turn.py` 翻译 | 加载阶段文案与工具明细 |
| `token` | `messages` 流正文，或节点 `custom{kind:"token"}`，或 `response_generator` 的最终 AI 消息 | 正文 Markdown / OpenUI |
| `interrupt` | HITL 门控 | 渲染表单，等待用户回答 |
| `done` | `turn.py`（先落库） | 结束加载，挂载 `build_result` 卡片 |

`done.build_result` 是 Java 结果的投影（8 类组件、总价、预算状态、兼容明细、逐件理由、`demo_offer_count`），前端按 `hardwareId` 关联逐件理由，不自行推断缺失字段。

## 9. 模型运行时

- Auto：Agent → Java 控制面解析出 `ResolvedRuntime`（provider、model_key、网关地址、密钥）；
- BYOK：Java 下发短期凭据租约，Agent 只在内存中使用；
- 统一走 LiteLLM，Agent 不直连厂商；
- 思考内容由 LiteLLM 归一为 `reasoning_content`，`llm.py` 保留到 `additional_kwargs`；
- 已知运维问题：平台托管 DeepSeek 密钥曾返回 401，导致个别回合无思考、正文退化为模板；代码已禁止静默降级，但密钥本身仍需更换。

## 10. 现有扩展点（重构可直接复用）

| 扩展点 | 位置 | 现状 |
| --- | --- | --- |
| 图节点与条件边 | `app/agent/pc/graph.py` | 单图固定装配，Profile 不能选图 |
| 工具注册 | `app/agent/registry.py` + `pc/tools.py` | 新增工具只需 `@register_tool` 并加入 Profile 的 `tools` |
| Agent Profile | `app/agents/pc-config.yaml` | `extra="forbid"`，启动期校验提示词与工具 |
| 提示词 | `app/agent/prompts/*.md` | 解析、生成、系统提示词分离 |
| RAG | `app/rag/` | 已有 `Retriever` / `Citation` / 权限过滤 / 提示词拼接，默认关闭 |
| HITL | `app/agent/pc/hitl.py` | 澄清与兼容确认两个门控，复用同一 `/chat/stream` + `resume` |
| 生命周期钩子 | `app/agent/hooks.py` | 请求前、模型输出后、流结束 |
| 质量评审 | `app/agent/pc/quality.py` | 确定性规则，可作为 LLM 评审的对照基线 |
| 评测 | `agent-service/evals/` | `python -m evals --fake` 可离线跑场景 |

## 11. 已知缺陷与风险

1. **LLM 完全不掌握候选实体**：状态里只有数量与聚合跑分，任何「LLM 选型」方案都必须先解决候选可见性与上下文预算问题。
2. **Java 候选池仍是启发式截断**：分组 + 分桶已修复整池失配，但仍是固定配额，不是按需求动态召回。
3. **场景/画像双轨**：`BuildScenario` 与 `WorkloadProfile` 语义重叠，`OFFICE` 只能靠场景权重表达，画像仍是 `GENERAL`。
4. **质量评审是规则补丁**：只能识别「CPU/GPU 价格比」和「办公显卡超支」，无法表达静音、体积、升级空间等真实偏好。
5. **平台托管密钥曾失效**：Auto 路径已改为 fail-fast，但密钥轮换仍待运维。
6. **目录存在重复型号**：多条 5080/5090（不同 `hardware_id`）未去重，可能占满候选池。
7. **`validate` 与 `solve` 双接口**：兼容规则只在 Java，Agent 无法在生成阶段预判，LLM 选型需要新增「候选校验」闭环。
8. **成本与延迟**：当前 LLM 只调用 1 次解析 + 1 次生成；改为多 Agent / 多轮选型后，token 与时延会显著上升，需要预算与降级策略。
9. **求解耗时已成瓶颈**：候选池分组后，`BuildSolverBenchmarkTests` 实测运行时目录 GAMING 15,000 元场景单次求解约 29 秒（9.5M 完整组合、p95 约 45 秒），无预算场景约 28.6 秒。工具超时已从 25 秒放宽到 60 秒以匹配真实耗时，但这是重构必须解决的性能债；任何「让 LLM 逐个评估候选」的方案都会再放大时延。

## 12. 重构约束与验收门禁

**硬约束**

- Java 是价格、库存、兼容性的唯一权威；Agent 不得自造型号、价格、链接；
- 依赖方向不可反转：Java 不调用 Agent；
- 契约变更（路径、字段、错误码、SSE 事件）必须同步：Agent Schema → Java DTO → 前端类型 → `docs/api-contract.md`；
- 不新增跨服务源码引用或共享业务表；
- 密钥、Token 只来自环境变量，日志不得输出敏感字段。

**门禁命令（仓库根）**

```powershell
corepack pnpm --dir frontend lint:ci
corepack pnpm --dir frontend type-check
corepack pnpm --dir frontend test:coverage

cd application-service; .\mvnw.cmd -q verify

uv --directory agent-service run ruff check app tests evals run.py
uv --directory agent-service run mypy
uv --directory agent-service run pytest -q --cov=app --cov-report=term-missing
uv --directory agent-service run python -m evals --fake
```

**建议的验收用例（沿用现有端到端场景）**

1. 「预算 20000 元以上，主要玩 2K 游戏」：CPU 不得为入门档，总价不得明显低于下界；
2. 「预算 12000–20000，家庭影音 / HTPC」：不出现旗舰显卡，场景为 `MEDIA`；
3. 「6000 元办公和网课，安静优先」：不默认配独显，`OFFICE` 权重生效；
4. 停掉 Java 控制面发起 Auto 对话：明确失败，不静默降级；
5. 刷新页面后：卡片、逐件理由、消息 ID 与反馈仍可关联。

## 13. 关键文件索引

| 关注点 | 文件 |
| --- | --- |
| 图与路由 | `agent-service/app/agent/pc/graph.py` |
| 节点实现 | `agent-service/app/agent/pc/nodes.py` |
| 状态与常量 | `agent-service/app/agent/pc/state.py`、`status.py` |
| 需求 Schema | `agent-service/app/agent/pc/schemas.py` |
| 工具封装 | `agent-service/app/agent/pc/tools.py`、`app/agent/registry.py` |
| 质量评审 | `agent-service/app/agent/pc/quality.py` |
| 渲染器 | `agent-service/app/agent/pc/renderer.py`、`openui_renderer.py` |
| 回合编排与 SSE | `agent-service/app/services/turn.py`、`app/api/v1/chat.py` |
| 模型解析 | `agent-service/app/services/model_resolver.py` |
| RAG | `agent-service/app/rag/` |
| Java 求解器 | `application-service/src/main/java/com/example/agent/pcbuild/application/BuildSolver.java` |
| 求解入口与快照 | `.../pcbuild/application/BuildSolveService.java`、`BuildSnapshotService.java` |
| 领域模型 | `.../pcbuild/domain/{BuildRequirements,BuildScenario,WorkloadProfile,BuildScoring,CompatibilityRule}.java` |
| 内网接口 | `.../pcbuild/web/PcBuildInternalController.java` |
| 契约文档 | `docs/api-contract.md` §5.7 |
| 现有方案文档 | `docs/pc-config/agent.md`、`solver-and-compatibility.md`、`recommendation-quality-remediation.md` |
