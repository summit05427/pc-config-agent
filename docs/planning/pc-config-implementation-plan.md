# PC 配置智能推荐 Agent 实施计划（阶段任务）

| 项 | 内容 |
| --- | --- |
| 状态 | Completed（Stage 1–6 完成） |
| 最后核验 | 2026-11-08 |
| 权威性 | 本文件是 PC 配置二次开发的任务拆分、阶段验收与差异记录依据；系统架构仍以 `docs/architecture-overview.md` 为准 |
| 需求方案 | `docs/planning/planning.md` |
| 代码基线 | `HEAD=136dc1b`，分支 `main`（含未提交改动，见 §3.1） |
| 执行进度 | 分支 `feature/pc-config-agent`；Stage 1–6 全部完成。`offers.json` 为 10 条 VERIFIED（京东自营/官方旗舰店实采）+ 18 条 MOCK（`price_source=MOCK_DEMO`，`data_status=MIXED_DEMO`）。Stage 2 Java `pcbuild` 与 7 个内部接口、V24 快照表已完成；Stage 3 Agent 单图替换完成（ruff/mypy 通过，pytest 504 用例、覆盖率 92.23%）；Stage 4 前端 PC 入口与 `BuildResultCard` 完成（lint/type-check 通过，483 用例、覆盖率 92.64%）；Stage 5 端到端联调完成，证据见 `docs/quality/pc-config-e2e-2026-11.md`；Stage 6 已建立 `docs/pc-config/` 12 份文档并同步根文档、环境变量与 `docs/planning/closure-plan.md` |

> `docs/planning/planning.md` 是需求方案，不是仓库现状。本文件基于源码与数据实测后编写；与方案冲突处集中在 §9。

## 1. 结论

**整体可行，前提是只保留一条工作流。** 现有模板已经把本次开发需要的基础设施都提供好了，真正的工作量只有三块：

1. **工作流替换**：把 `model ⇄ tools` 的通用 ReAct 图整体换成 PC 配置流水线，而不是新增一张图与它并存。
2. **数据收敛**：8,238 条 PCD 数据 → 19–30 款可求解候选；补齐兼容性字段与 PassMark 映射；替换为中国区人工核验报价。
3. **求解与展示**：Java 侧确定性求解 + 兼容性校验 + 快照落库；Agent 侧编排与确定性渲染；前端结构化卡片。

### 1.1 可行性评分

| 维度 | 结论 | 依据 |
| --- | --- | --- |
| 技术可行性 | 高 | 图装配入口唯一、工具治理完备、SSE 与内部鉴权已存在 |
| 数据可行性 | 中 | 硬件与跑分充足；中国区报价必须人工提供，无法自动获得 |
| 契约兼容性 | 高 | `done` 只追加可选字段，SSE 事件类型与既有 payload 形状不变 |
| 回归风险 | 中高 | 删除通用图会连带删除一批测试，必须同步补齐 PC 图测试 |
| 工期可行性 | 中 | 方案 P0+P1 全量偏大；本文件已收敛范围并给出可切分阶段 |

## 2. 已确认决策

以下决策由项目负责人于 2026-11-08 确认，是本计划唯一输入。

| 编号 | 决策 | 影响 |
| --- | --- | --- |
| D1 | 工作流形态为**确定性流水线**，LLM 只出现在 `requirement_parser` 与 `response_generator` | 删除 ReAct 循环；节点固定、可单测、结果可复现 |
| D2 | 各节点**直接调用治理后的工具**；`turn.py` 增加“节点 → 工具事件”映射；解析节点的 LLM 调用打 `TAG_NOSTREAM` | SSE 事件类型与 payload 形状不变；用户仍能看到工具进度 |
| D3 | 信息不足时采用**无状态重提**：返回追问，用户补充后重新提交 | 不引入 `interrupt/resume`，不改 `/chat/stream` 契约 |
| D4 | 报价使用**负责人提供的中国区人工核验清单**；无有效报价时 fail-closed | 不折算美元、不编造价格与链接 |
| D5 | 结果**双通道**：`done` 事件追加可选 `build_result`，前端渲染卡片；Markdown 兜底 | 事件类型不变，旧客户端忽略新字段即可 |
| D6 | Build 快照**落库**（V24 append-only 表）+ `GET /internal/v1/pc/builds/{id}` | 支撑未来对比、瓶颈分析与硬件替换 |
| D7 | 保留 Profile 加载与校验机制，但仓库只保留 `pc-config.yaml`；删除通用图与示例人格 | 单图单 Profile；未知 `agent_id` 仍返回 404 |
| D8 | 硬件数据使用 **JSON fixture + Repository 端口** | 迭代快；未来换 PostgreSQL 不改 Solver 与工具契约 |

对应架构决策记录：

- `docs/adr/0009-single-pc-workflow-over-generic-chat.md`（单图 + 确定性流水线）
- `docs/adr/0010-deterministic-markdown-build-output.md`（确定性渲染 + `done.build_result`）
- `docs/adr/0011-manually-verified-offer-dataset.md`（人工核验报价）
- `docs/adr/0012-persist-build-snapshot.md`（快照落库）

## 3. 基线事实

### 3.1 工作区状态

- 当前分支 `main`，`HEAD=136dc1b`。
- 已修改未提交：`docs/deployment/deployment-guide.md`、`frontend/src/core/http/auth.ts`、`frontend/src/core/http/auth.spec.ts`、`frontend/src/features/sessions/api/request.ts`、`frontend/src/features/sessions/api/request.spec.ts`、`scripts/dev/start-local.ps1`。
- 未跟踪：`docs/planning/`、`docs/pc-config/`、`docs/adr/0009-0011`、`scripts/dev/preflight.ps1`。
- **约束**：实施前创建 `feature/pc-config-agent` 分支；不清理、不覆盖上述修改。

### 3.2 可直接复用的能力（源码级已验证）

| 能力 | 证据 | 复用方式 |
| --- | --- | --- |
| 图装配唯一入口 | `agent-service/app/services/model_runtime.py` 的 `_default_graph` / `prepare_agent` | 只替换图工厂，路由与传输层不动 |
| 图组装入口 | `agent-service/app/agent/graph.py` 的 `build_agent` | 保留函数签名，替换内部节点与边 |
| 请求级 Profile | `agent-service/app/api/v1/chat.py` 的 `resolve_profile`、`agent-service/app/agent/profiles.py` | 只保留 `pc-config` 一个 YAML |
| 工具治理 | `agent-service/app/agent/registry.py` 的 `ToolSpec` / `register_tool` / `build_tools` | 5 个 PC 工具直接注册 |
| SSE 事件 | `agent-service/app/api/v1/sse.py`、`agent-service/app/services/turn.py` 的 `TurnEventType` | 事件类型零变更 |
| 内部调用鉴权 | `agent-service/app/services/control_plane.py`（服务令牌 + `X-User-Token`） | 抽取令牌缓存后复用 |
| Java 内部接口 | `application-service/.../shared/security/TokenUseFilter.java`、`shared/api/ApiResponse.java` | 新模块沿用服务令牌 |
| 模块化结构 | `application-service/.../identity`、`model` 的 `package-info.java` | `pcbuild` 作为第三个业务模块 |
| 数据库迁移 | `application-service/src/main/resources/db/migration/`（最高 `V23`） | 新增 `V24` 快照表 |
| 前端 SSE 与 Markdown | `frontend/src/features/sessions/api/stream-chat.ts`、`frontend/src/features/chat/components/markdown-content.tsx` | 直接复用，追加卡片渲染 |

### 3.3 传输层硬约束（决定 PC 图必须遵守的契约）

| 约束 | 证据 | 结论 |
| --- | --- | --- |
| 图输入固定包含 `messages` / `preference_prompt` / `use_history` | `turn.py` 的 `_agent_events` | `PCConfigState` 必须包含这三个字段 |
| 历史落库读取 `state["messages"]` | `turn.py` 的 `_persist_turn` | `response_generator` 必须把最终回答写入 `messages` |
| 只有节点名 `model` 才产生 `tool_call` | `turn.py` 的 `_node_message_events` | 通过节点返回 `tool_events` + `turn.py` 映射补齐 |
| 内部 LLM 可屏蔽流式输出 | `agent-service/app/agent/memory.py` 使用 `TAG_NOSTREAM` | 解析节点调用打该标签，避免 JSON 漏进正文 |
| Profile 不能选择图 | `profiles.py` 的 `extra="forbid"` | 不做 dispatcher，直接单图 |
| 前端从不发送 `agent_id` | `frontend/src/features/sessions/api/types.ts` | 单一入口，默认 Profile 固定 |

### 3.4 硬阻塞与风险

| 编号 | 问题 | 证据 | 处理 |
| --- | --- | --- | --- |
| R1 | 现有 `price` 列标注为 USD，但数值量级与人民币一致（如 9800X3D 为 3088.80、RTX 5090 约 3.1 万），币种存疑；链接指向 PCPartPicker，无中国区商家报价 | `Hardware data/README.md` §4 与实测冲突 | 该列只作参考价，不参与预算；D4 人工录入中国区报价 |
| R2 | 规格字段是未归化字符串，多值用换行分隔 | 同上 §4.2、§4.3 | Stage 1.2 归一化脚本 |
| R3 | PassMark `socket` 缺 31%、GPU `tdp` 缺 73% | 同上 §4.5 | 30 款候选逐条人工补齐；缺失标记 `UNKNOWN` |
| R4 | 硬件名与 PassMark `model_key` 需归一化匹配 | 同上 §4.6 | 30 款候选逐条人工建映射 |
| R5 | 八类候选笛卡尔积过大 | 本文件 §7.4 | 候选过滤 + 每类上限 + 剪枝 + 分支限界 |
| R6 | 删除通用图会牵连大量测试 | `agent-service/tests/test_agent_graph.py`、`evals/` | 同步改写为 PC 图测试，禁止删断言换通过率 |
| R7 | `docs/planning/closure-plan.md` 被 `docs/README.md` 引用但不存在 | 文件系统核查 | Stage 6 创建或改链 |
| R8 | `planning.md` 写 PassMark 23,945，实际 25,318 | `Hardware data/README.md` §1 | 以本文件与数据实测为准 |

## 4. 目标架构

```text
Frontend（单一 PC 配置入口）
  └─ 复用会话 / 历史 / 模型选择 / 偏好 / SSE 消费 / Markdown 渲染
     + 新增 BuildResultCard（读 done.build_result）
        │  POST /agent/api/v1/chat/stream
        ▼
Agent Service
  └─ PC Configuration Graph（唯一图）
       START
         → requirement_parser        LLM 结构化输出（TAG_NOSTREAM）
         → requirement_validator     纯代码校验；不足 → 追问
         → candidate_retriever       工具：search_hardware_candidates
         → build_solver              工具：solve_pc_build（Java 内落快照）
         → build_validator           工具：validate_pc_build；失败最多重解 1 次
         → response_generator        LLM 写摘要/理由 + 代码渲染 Markdown
         → END
        │  工具调用：服务令牌 + X-User-Token
        ▼
Java Application Service
  └─ pcbuild 模块
       Repository 端口：HardwareCatalog / Benchmark / Offer / BuildSnapshot
       适配器：classpath JSON fixture + PostgreSQL 快照表
       CompatibilityValidator / BuildSolver / BuildSnapshotService
```

**职责边界不变**：Java 是硬件、跑分、报价、求解、兼容性、预算与快照的权威；Agent 只做意图解析、编排、解释与输出；Agent 不访问 Java 数据库。

### 4.1 工作流契约

| 项 | 约定 |
| --- | --- |
| 图输入 | `messages`（含本轮 `HumanMessage`）、`preference_prompt`、`use_history` |
| 图输出 | `response_generator` 返回 `messages: [AIMessage(final_markdown)]` + `build_result` |
| 内部状态 | `requirements`、`validation_result`、`candidate_pool`、`build_result`、`compatibility_report`、`budget_report`、`retry_count`、`workflow_status`、`tool_events` |
| 循环上限 | `retry_count ≤ 1`；`recursion_limit` 保持全局配置 |
| 工具事件 | 节点返回 `tool_events: [{"phase": "start"|"end", "name": ..., "args"?: ..., "preview"?: ...}]`，由 `turn.py` 映射为既有 `tool_call` / `tool_result` 事件 |
| 追问 | `workflow_status=clarification`，`response_generator` 输出追问文本，不产生 `build_result` |
| 失败 | 解析失败 / 无候选 / 无解 / 上游不可用，分别返回结构化状态与安全文案 |

`PCConfigState` 必须与 `AgentState` 的 `messages`、`preference_prompt`、`use_history` 字段兼容，否则 `turn.py` 需要大改。这是本计划优先保证的兼容点。

## 5. 阶段任务

| 阶段 | 依赖 | 可并行项 |
| --- | --- | --- |
| Stage 0 基线与边界 | 无 | 文档与 ADR |
| Stage 1 数据与报价 | Stage 0；1.4 需外部清单 | 1.1–1.3、1.5–1.6 可先做 |
| Stage 2 Java pcbuild | Stage 1 的 fixture | Repository / 兼容规则 / Solver 可并行 |
| Stage 3 Agent 单图重构 | Stage 2 的内部接口 | 删除通用图与写 PC 图可并行评审 |
| Stage 4 前端单一入口 | Stage 3 的输出契约 | 空态与样式可先做 |
| Stage 5 联调回归 | Stage 1–4 | 基础设施回归可与业务联调并行 |
| Stage 6 文档收尾 | Stage 5 证据 | 文档可与 Stage 5 交叉进行 |

### Stage 0 基线与改造边界

**目标**：锁定工作区与删除范围，避免误删未提交修改。

**任务**

- 0.1 创建 `feature/pc-config-agent`，记录 `git status` 与 `HEAD`。
- 0.2 输出删除 / 保留清单（§6），逐项标注调用点证据。
- 0.3 确认不修改 §3.1 的未提交文件。
- 0.4 把本文件、ADR-0009/0010/0011/0012、`docs/pc-config/glossary.md` 纳入版本控制。

**产出**：本文件、4 份 ADR、术语表。

**验收**：删除清单每项都有调用点证据；保留清单覆盖会话、历史、模型选择、偏好、SSE、鉴权。

**风险**：删除是破坏性变更，必须单独提交并保留 `git revert` 路径。

### Stage 1 候选数据与报价

**目标**：得到 19–30 款、八类齐全、可直接参与求解的结构化数据。

**任务**

- 1.1 `scripts/pc-config/select_candidates.py`：按类别、品牌、价格、规格完整度筛选，输出候选清单。
- 1.2 `scripts/pc-config/normalize_specs.py`：解析 socket、DDR 类型、板型、最大显卡长度、最大散热器高度、电源功率与供电接口、散热器 socket 支持、M.2/SATA；单位统一，缺失写 `null` 并记录原因。
- 1.3 建立 PassMark 映射：CPU 用 `model_key`，GPU 用归一化型号；记录 `match_method` 与 `match_confidence`；无法匹配保留并标记 `benchmark_missing`。
- 1.4 录入负责人提供的中国区报价清单，字段见 §7.3；填写 `docs/pc-config/offers.template.json`，由 `scripts/pc-config/ingest_offers.py` 校验并转换为 `offers.json`；每条必须有商家、平台、人民币分价、链接、核验时间、有效期。
- 1.5 生成 fixture：`application-service/src/main/resources/pc-config/{catalog,benchmarks,offers}.json`。
- 1.6 为每条硬件写 `data_quality_status`、`lifecycle_status`、`recommendation_status`。

**产出**：两个脚本、三份 fixture、候选清单评审记录。

**验收**

- 八类均有候选；CPU、GPU、主板各至少 2 个备选。
- 每件硬件的求解必需字段不为 `null`，或明确标记为不可参与求解。
- 报价 `match_status=VERIFIED`、`price_fen` 为正整数、`purchase_url` 为人工核验链接。
- 抽查 5 条报价与源页面一致；无编造价格或链接。

**风险**：1.4 未到位时阻塞，但 1.1–1.3、1.5–1.6 可先做。

### Stage 2 Java pcbuild 模块

**目标**：把查询、兼容性、求解、预算与快照做成可被 Agent 调用的内部 API。

**任务**

- 2.1 新建 `com.example.agent.pcbuild`，`package-info.java` 标注 `@ApplicationModule`；分层 `domain` / `application` / `infrastructure` / `web`。
- 2.2 Repository 端口：`HardwareCatalogRepository`、`BenchmarkRepository`、`OfferRepository`、`BuildSnapshotRepository`；JSON fixture 适配器不向上层暴露文件细节。
- 2.3 `HardwareCatalogService`、`BenchmarkQueryService`、`OfferQueryService`。
- 2.4 `CompatibilityValidator`：8 条规则、4 种状态（`PASS` / `WARNING` / `FAIL` / `UNKNOWN`）、`rule_version`。
- 2.5 `BuildSolver`：候选过滤 → 兼容性剪枝 → 预算剪枝 → 确定性搜索 → 场景评分；金额全部 `long` 分。
- 2.6 快照：求解成功后在同一事务写入 `pc_build_snapshots`（V24），返回 `build_id`。
- 2.7 内部接口（`ApiResponse` + 服务令牌）：
  - `GET /internal/v1/pc/hardware/candidates`
  - `GET /internal/v1/pc/hardware/{hardwareId}`
  - `GET /internal/v1/pc/benchmarks`
  - `GET /internal/v1/pc/offers`
  - `POST /internal/v1/pc/builds/solve`
  - `POST /internal/v1/pc/builds/validate`
  - `GET /internal/v1/pc/builds/{buildId}`
- 2.8 测试：Repository、Benchmark 映射、Offer 状态、Solver、预算边界、8 条兼容规则、快照归属、API 集成。

**产出**：`application-service/src/main/java/com/example/agent/pcbuild/**`、`V24__create_pc_build_snapshots.sql`、测试。

**验收**

- 相同输入多次求解结果一致。
- 超预算方案数为 0；已知 `FAIL` 组合进入成功方案次数为 0；`UNKNOWN` 不被展示为 `PASS`。
- 无解返回结构化原因，不放宽预算。
- 金额全为整数分，响应经 `ApiResponse` 包装。
- 快照只能被所属用户读取。

**风险**：兼容规则依赖 Stage 1 归一化字段；字段缺失必须返回 `UNKNOWN`，不得跳过规则。

### Stage 3 Agent 单图重构

**目标**：删除通用 ReAct 图，建立唯一的 PC Configuration Graph。

**任务**

- 3.1 按 §6 删除通用图、示例 Profile 与 Prompt、通用图测试与评测用例。
- 3.2 定义 `PCConfigState`：包含 `messages`、`preference_prompt`、`use_history` 以及 §4.1 的业务字段；`tool_events` 用 `operator.add` 累加。
- 3.3 实现节点：
  - `requirement_parser`：LLM Structured Output + Pydantic Schema，调用打 `TAG_NOSTREAM`。
  - `requirement_validator`：纯代码校验预算、场景、范围、硬约束冲突与缺失信息。
  - `candidate_retriever`：调用 `search_hardware_candidates`。
  - `build_solver`：调用 `solve_pc_build`，Agent 不自行选 SKU。
  - `build_validator`：调用 `validate_pc_build`，失败最多重解 1 次。
  - `response_generator`：LLM 生成摘要与理由；型号、价格、链接、总价由代码模板渲染。
- 3.4 条件边：追问 / 无候选 / 无解 / 重试 / 正常结束，全部有显式分支与上限。
- 3.5 注册 5 个工具：`search_hardware_candidates`、`get_benchmark_data`、`get_verified_offers`、`solve_pc_build`、`validate_pc_build`；声明超时、重试、输出上限、单轮配额。
- 3.6 新增 Prompt：`pc_config_system.md`、`requirement_parser.md`、`response_generator.md`。
- 3.7 单一 Profile：`agent-service/app/agents/pc-config.yaml`，`AGENT__DEFAULT_PROFILE=pc-config`。
- 3.8 传输适配：`turn.py` 增加 `tool_events` → `tool_call` / `tool_result` 映射；`done` 事件追加可选 `build_result`。
- 3.9 内部客户端：抽取服务令牌缓存为共享模块，新增 PC 内部 API 客户端，不复制令牌逻辑。
- 3.10 测试：Schema、硬约束/软偏好、路由、节点 IO、工具治理、无候选、预算无解、重试上限、Fake LLM 五路径、输出与 Java `BuildResult` 一致性。

**产出**：`agent-service/app/agent/pc/**`（图、State、节点、渲染器）、工具、Prompt、Profile、传输适配、测试。

**验收**

- Fake LLM 下跑通成功、追问、无候选、无解、上游不可用五条路径。
- 任何循环都有上限；不存在无限重试。
- `response_generator` 不产生硬件型号、价格、链接；这些字段全部来自 `BuildResult`。
- 解析节点的 JSON 不出现在 SSE 正文流。
- 工具错误不被伪装成正常推荐。

**风险**：删除通用图会连带删除大量测试；必须同步补齐 PC 图测试，不得降低断言。

### Stage 4 前端单一 PC 入口

**目标**：把聊天页收敛为 PC 配置入口，完整展示 11 项必需信息。

**任务**

- 4.1 保留 `frontend/src/routes/pages/chat-page.tsx` 作为唯一业务入口；移除 writer / 多 Profile 文案与入口。
- 4.2 请求固定使用默认 `pc-config`；`agent_id` 若保留仅接受该值。
- 4.3 扩展 SSE 类型：`done` 事件可选 `build_result`；旧字段不变。
- 4.4 新增 `BuildResultCard`：展示需求总结、八件硬件、主要参数、单价、购买链接、PassMark、总价、预算状态、兼容性状态、核验时间、推荐说明。
- 4.5 无 `build_result` 时回退到 `MarkdownContent`；链接加 `target="_blank"` 与 `rel="noopener noreferrer"`。
- 4.6 空态：追问、无候选、无解、上游错误、预算状态、兼容性状态。
- 4.7 保留会话列表、历史、会话级模型选择、聊天偏好。
- 4.8 测试：八硬件渲染、链接、总价、预算状态、兼容性状态、无解、Markdown 回退、基础设施回归。

**验收**

- 11 项信息完整可见；价格与链接全部来自后端字段。
- 历史会话可回放；模型选择与偏好仍生效。
- 窄屏下卡片可读，Markdown 回退不丢信息。

**风险**：卡片改动触及 `stream-chat.ts` 类型与渲染层；必须保证旧会话（无 `build_result`）正常回放。

### Stage 5 端到端联调与回归

**目标**：证明整条链路可演示，基础设施未回归。

**任务**

- 5.1 本地启动 Java、Agent、Postgres、LiteLLM；确认迁移与 fixture 加载。
- 5.2 固定 3 组 Demo 输入：预算可行、预算不可行、缺关键信息需追问。
- 5.3 逐项核对 §8 指标。
- 5.4 基础设施回归：登录、刷新、会话列表、历史、SSE 七类事件、模型选择、偏好。
- 5.5 记录联调证据：请求、响应、截图或日志摘要。

**产出**：`docs/quality/pc-config-e2e-2026-11.md`（一次性报告，标注 `Completed`）。

**验收**：§8 全部指标通过；基础设施回归无新增失败。

### Stage 6 文档与收尾

**目标**：后续 Agent 只读文档即可继续开发。

**任务**

- 6.1 建立 `docs/pc-config/` 文档集：`README.md`、`demo-scope.md`、`architecture.md`、`agent-workflow.md`、`agent-state-and-tools.md`、`data-model.md`、`data-quality-and-lifecycle.md`、`market-offer-management.md`、`solver-and-compatibility.md`、`api-contract.md`、`testing-and-evaluation.md`、`extension-roadmap.md`。
- 6.2 更新 `docs/api-contract.md` 与 `docs/services/agent-service/api-reference.md`：内部接口、`done.build_result` 可选字段、Profile 变更、事件类型不变声明。
- 6.3 更新 `docs/architecture-overview.md`：PC 模块职责、图变更、未实现能力。
- 6.4 更新 `docs/README.md` 与 `docs/INDEX.md`；处理 `closure-plan.md` 缺失。
- 6.5 新增环境变量同步 `.env.example` 与 `docs/deployment/environment-variables.md`。
- 6.6 运行文档门禁：`scripts/check-doc-links.ps1`、`scripts/check-env-docs.ps1`。
- 6.7 输出最终报告：改动文件、真实图结构、接口、数据来源、未实现项、与方案差异、测试结果、下一阶段入口。

**验收**：文档链接检查通过；描述与代码一致；未实现内容标注【未实现】。

## 6. 删除与保留清单

### 6.1 删除

| 对象 | 位置 | 依据 |
| --- | --- | --- |
| 通用 ReAct 图装配 | `agent-service/app/agent/graph.py` 中 `model` / `tools` 节点与 `tools_condition` | D1：确定性流水线 |
| 默认与示例 Profile | `agent-service/app/agents/default.yaml`、`agent-service/app/agents/examples/writer.yaml` | D7：只保留 `pc-config` |
| 通用 Prompt | `agent-service/app/agent/prompts/default.md`、`writer.md` | 被 PC Prompt 替代 |
| 通用图测试 | `agent-service/tests/test_agent_graph.py` 的 ReAct 断言 | 改写为 PC 图测试，不得简单删除 |
| 通用图评测用例 | `agent-service/evals/cases/example.yaml` 及相关 runner 装配 | 改造为 PC 图评测 |
| 前端通用聊天文案与入口 | `frontend/src/routes/pages/chat-page.tsx`、`frontend/src/routes/router.tsx` | 只保留 PC 配置语义 |
| OpenUI 演示路由 | `frontend/src/routes/pages/openui-demo-page.tsx` | D7：不作为展示前置 |

### 6.2 保留

| 对象 | 位置 | 原因 |
| --- | --- | --- |
| 聊天传输层 | `agent-service/app/api/v1/chat.py` | 会话锁、幂等、SSE 响应仍需要 |
| SSE 编码与事件翻译 | `agent-service/app/api/v1/sse.py`、`agent-service/app/services/turn.py` | 事件类型不变；仅增加节点事件映射与 `done` 可选字段 |
| Profile 加载与校验 | `agent-service/app/agent/profiles.py` | 复用启动期校验；仓库只留一个 YAML |
| 会话存储 | `agent-service/app/services/session_store/**` | 保留会话列表与历史 |
| 模型运行时 | `agent-service/app/services/model_runtime.py`、`model_resolver.py` | 保留会话级模型选择 |
| 工具治理 | `agent-service/app/agent/registry.py` | PC 工具继续使用 |
| 鉴权 | `agent-service/app/api/v1/auth.py` | 基础设施回归 |
| 前端聊天运行时 | `frontend/src/features/chat/**`、`frontend/src/features/sessions/**` | 复用 SSE 消费与 Markdown 渲染 |
| 模型选择与偏好 | `frontend/src/features/models/**`、设置页 | D7 明确保留 |

## 7. 关键数据契约

### 7.1 金额

所有金额使用 `long` 分；禁止 `float` / `double` 参与金额计算；展示层格式化为元。

### 7.2 Hardware / Benchmark

| 对象 | 必需字段 |
| --- | --- |
| Hardware | `hardware_id`、`category`、`brand`、`model_name`、`specifications`、`data_quality_status`、`lifecycle_status`、`recommendation_status` |
| Benchmark | `hardware_id`、`benchmark_type`、`score`、`source`、`match_method`、`match_confidence` |

### 7.3 Marketplace Offer

| 字段 | 说明 |
| --- | --- |
| `offer_id` | 商品记录唯一标识 |
| `hardware_id` | 对应标准硬件 |
| `platform` | 京东 / 淘宝 / 天猫等 |
| `platform_sku` | 平台商品 ID |
| `seller` | 商家 |
| `title` | 商品标题 |
| `price_fen` | 人民币分，正整数 |
| `price_type` | 普通价 / 促销价 / 会员价 |
| `purchase_url` | 人工核验链接 |
| `verified_at` | 核验时间 |
| `valid_until` | 报价有效期 |
| `match_status` | 必须为 `VERIFIED` 才能进入推荐 |

### 7.4 BuildResult

必需字段：`build_id`、`components`（八类各一）、`total_price_fen`、`budget_max_fen`、`budget_status`、`compatibility_report`、`benchmark_snapshot`、`offer_snapshot`、`solver_version`、`compatibility_rule_version`、`catalog_version`、`created_at`。

求解搜索策略：按类别过滤后设置每类候选上限（建议 CPU/GPU ≤ 12、其余 ≤ 8），先做兼容性剪枝再做预算剪枝，使用分支限界按“场景评分 / 价格”排序；同一输入必须得到同一结果（稳定排序 + 固定 tie-break）。

### 7.5 `done.build_result`（前端消费子集）

| 字段 | 说明 |
| --- | --- |
| `build_id` | 快照标识 |
| `components[]` | `category`、`model_name`、`spec_summary`、`price_fen`、`purchase_url`、`benchmark`、`offer_verified_at` |
| `total_price_fen` / `budget_max_fen` / `budget_status` | 总价与预算 |
| `compatibility[]` | `rule`、`status`、`message` |
| `reason_summary` | 推荐说明（LLM 生成，不含型号/价格/链接） |

## 8. 测试与业务指标

### 8.1 测试矩阵

| 层 | 必测 |
| --- | --- |
| Java | Repository、Benchmark 映射、Offer 状态、Solver、预算边界、8 条兼容规则、快照归属、API 集成 |
| Agent | Parser Schema、硬约束/软偏好、路由、节点 IO、工具治理、无候选、预算无解、重试上限、Fake LLM 五路径、`TAG_NOSTREAM`、输出一致性 |
| Frontend | 八硬件渲染、链接、总价、预算状态、兼容性状态、无解、Markdown 回退、会话/历史/模型选择/偏好回归 |

### 8.2 业务指标

- 成功配置恰好包含八个类别。
- 严格预算超支次数为 0。
- 已知硬性兼容冲突进入成功方案次数为 0。
- 虚构商品链接次数为 0、虚构价格次数为 0。
- 无法验证的关键规格不得展示为已兼容。
- 工具错误不得伪装为正常推荐。

### 8.3 回归基线

只保留基础设施回归：登录、刷新、会话列表、历史、SSE 七类事件、模型选择、偏好。默认聊天业务的断言随代码删除，但不得用“删测试”换取通过率。

## 9. 与 `docs/planning/planning.md` 的差异

| 方案位置 | 方案原文 | 实际处理 | 原因 |
| --- | --- | --- | --- |
| §3.2 / §7.1 | 保留通用 ReAct Graph，通过 Profile 分流 | 删除通用图，只保留 PC 图 | D1 / D7；ADR-0009 |
| §5.2 | 提供 `POST /internal/v1/pc/builds/snapshots` | 由 `solve` 内聚落库，另提供 `GET /builds/{id}` | D6；ADR-0012 |
| §5 | 求解结果仅内存返回 | 落库 append-only 快照 | D6 |
| §7.5 | 5 个 PC 工具 | 保留 | 与现有工具治理匹配 |
| §9 | 不新增 SSE 事件 | 事件类型不变；`done` 追加可选 `build_result` | D5；ADR-0010 |
| §9 | OpenUI 可复用 | 不作为前置，删除 demo 路由 | D7 |
| §12 P1 | 版本化数据模型 | 本期只加快照表，不做硬件版本化 | 范围收敛 |
| §14 / §15 | 原有功能回归 | 改为基础设施回归 | D7 |
| §13 | 建立 `docs/pc-config/` 全套文档 | Stage 6 交付，不预建空文档 | 文档治理禁止空洞文档 |
| §1 | 引用 `docs/planning/closure-plan.md` | 文件不存在 | R7 |
| §1 | PassMark 23,945 条 | 实际 25,318 条 | R8 |

### 9.1 相对上一版计划的修订

上一版计划（同日早先草稿）选择“纯 Markdown 展示、不落库、不改 `turn.py`”。本轮确认后改为：

| 项 | 上一版 | 现版本 |
| --- | --- | --- |
| 结果展示 | 仅 Markdown | `done.build_result` 卡片 + Markdown 兜底 |
| Build 持久化 | 不落库 | V24 快照表 + 查询接口 |
| 工具事件 | 不产生 | 节点 `tool_events` + `turn.py` 映射 |
| 解析节点流式 | 未处理 | `TAG_NOSTREAM` 屏蔽 |
| Profile | 删除多 Profile 解析 | 保留校验机制，只留 `pc-config` |

## 10. 待确认事项

| 编号 | 事项 | 阻塞阶段 | 需要谁 |
| --- | --- | --- | --- |
| O1 | 19–30 条中国区商品报价清单（标题、商家、平台、分价、链接、核验时间、有效期） | Stage 1.4 | 项目负责人 |
| O2 | 候选品牌/型号范围（AMD/Intel、NVIDIA/AMD） | Stage 1.1 | 项目负责人 |
| O3 | 快照保留策略（本期只增不删是否需要保留期限） | Stage 6 | 项目负责人 |

## 11. 本期不做

- 全量 8,238 条数据清洗。
- 商品自动采集、爬虫、电商 API、自动 SKU 匹配。
- 硬件数据版本化与历史价格曲线。
- OR-Tools。
- RAG、MCP、HITL、多 Agent。
- 多方案对比、瓶颈分析、交互式硬件替换。
- 管理端硬件/商品维护页面。
- OpenUI 生成式配置卡片。
