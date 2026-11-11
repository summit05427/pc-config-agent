# Stage 11：Agent 高级能力体系建设——完整实施任务

## 一、任务目标

你是一名资深 AI Agent 架构师，熟悉 Python、LangChain、LangGraph、RAG、HITL、Agent Evaluation、Observability 和企业级 Agent 系统设计。

当前项目是一个基于 LLM 的 PC 配置智能推荐 Agent 应用。本阶段需要在现有四端架构和 Stage 1–10 的基础上，对 Agent Service 进行系统性能力升级。

Stage 11 的核心目标：

1. 建立专业的 RAG 硬件知识检索体系。
2. 建立基于 LangGraph 持久化执行机制的 HITL 人机协作能力。
3. 建立 Agent Evaluation 评估体系，能够量化和验证 Agent 的实际表现。
4. 完善 Agent Observability，能够追踪 Graph、LLM、工具调用和检索过程。
5. 完善 Guardrails 与 Tool Governance，限制 Agent 的错误行为。
6. 完善 Context Engineering，提升上下文组织、历史信息处理和 Token 使用效率。
7. 评估 Memory 长期记忆能力，为后续用户偏好管理做好准备。
8. 评估 MCP 与 Multi-Agent 的实际应用价值，只有存在明确需求时才引入。

**本阶段的目标不是让 Agent 使用尽可能多的技术，而是让它具备可靠的知识获取、用户协作、工具调用、上下文管理和自我评估能力。**

---

# 二、项目现有架构与必须继承的设计

## 2.1 四端架构

项目采用 Monorepo：

服务

技术栈

职责

frontend

React 19 + TypeScript + Vite

用户交互、聊天和配置结果展示

admin

React 19 + shadcn-admin

独立管理端

application-service

Java 21 + Spring Boot + Spring Modulith

业务数据、硬件、报价、兼容性、预算和快照

agent-service

Python 3.12 + FastAPI + LangGraph + LangChain

Agent 工作流、知识检索、工具编排和结果解释

基础设施包括：

- PostgreSQL；
- Redis；
- LiteLLM；
- Nginx；
- SSE；
- OpenUI 相关 React UI 能力。

具体依赖版本、数据库实例、现有服务能力必须以当前仓库为准。

## 2.2 当前 Agent 工作流

现有 PC Agent 使用确定性 LangGraph 流程：

`START → requirement_parser → requirement_validator → candidate_retriever → build_solver → build_validator → response_generator → END`

现有工具：

- `search_hardware_candidates`
- `get_benchmark_data`
- `get_verified_offers`
- `solve_pc_build`
- `validate_pc_build`

已有 `PCConfigState` 需要兼容：

- `messages`
- `preference_prompt`
- `use_history`
- 当前 PC 配置业务状态字段。

必须检查这些字段在当前代码中的实际定义和使用方式。

不能直接重写现有 Graph，也不能将确定性业务节点改造成自由发挥的 LLM Agent。

## 2.3 核心业务权威边界

必须继续遵守：

**Java Application Service 是 PC 业务决策的唯一权威。**

Java 负责：

- 硬件目录；
- Benchmark；
- Marketplace Offer；
- 兼容性校验；
- 工作负载评分；
- 预算校验；
- BuildSolver；
- BuildSnapshot。

Agent 负责：

- 用户需求理解；
- 上下文组织；
- 外部技术知识检索；
- 工具调用；
- 需求澄清；
- 必要的用户确认；
- 配置解释和交互协调。

RAG 不得取代 Java 硬件目录、Benchmark、报价或兼容性规则。

HITL 不得让用户通过确认操作绕过 Java 的硬性约束。

LLM 不得自行编造硬件型号、价格、兼容性结论或 Benchmark 数据。

## 2.4 需要继承的现有约束

1. Agent 不直接访问 Java 数据库。
2. Agent 通过现有 Java 内部 API 获取业务数据。
3. ToolSpec 继续作为工具治理基础。
4. 不新增 Agent 微服务。
5. 不新增不必要的微服务或消息队列。
6. 不重做现有 SSE 和前端聊天架构。
7. 不替换已经完成的 React/OpenUI 对话界面。
8. 不因引入 RAG 而将硬件价格和 Benchmark 数据迁移到向量数据库。
9. 不为了使用 Multi-Agent 而拆分现有确定性 Graph。
10. 所有新增能力必须可以测试、追踪和验证。

---

# 三、Stage 11.0：现有 Agent 架构与能力基线审计

开始修改代码前，先对当前实现进行完整审计。

### 3.1 Agent Service

检查：

- 当前 LangGraph Graph；
- `PCConfigState`；
- 每个 Node 的职责；
- State reducer；
- ToolSpec；
- 工具注册与执行机制；
- Prompt 管理；
- 模型调用和 LiteLLM 集成；
- 上下文历史管理；
- SSE 流式输出；
- Checkpointer；
- PostgreSQL Checkpointer 是否已经部署和启用；
- Agent 异常处理；
- Agent 测试；
- 当前日志及可观测能力。

### 3.2 Frontend

检查：

- 当前 React 对话界面；
- OpenUI 集成方式；
- SSE 消费；
- 现有消息类型；
- 工具调用与工具结果展示；
- citations 展示；
- 对话状态恢复；
- 会话与 thread_id 的关联；
- 用户输入和结构化表单能力。

HITL 需要与现有 UI 协作，不允许为了增加确认界面重做整个聊天系统。

### 3.3 Java Application Service

检查：

- 用户身份和会话权限；
- 用户偏好存储；
- 内部 API 鉴权；
- Agent 与 Java 的用户令牌传递；
- BuildSnapshot；
- 日志和链路追踪能力；
- 当前数据库表和迁移状态。

### 3.4 基线报告

产出：

`docs/pc-config/stage-11-readiness-report.md`

必须明确：

1. 哪些能力已经实现；
2. 哪些能力只有基础接口；
3. 哪些能力完全缺失；
4. 当前 LangGraph 是否具备可靠持久化能力；
5. 哪些现有代码可以直接复用；
6. 各项功能的契约影响；
7. 哪些功能存在依赖或阻塞。

**不要重复开发已有能力。发现现有实现满足要求时，应当保留它。**

完成基线审计后，继续实施可以独立推进的任务。只有出现真实阻塞时才暂停对应部分。

---

# 四、Stage 11.1：Agent 基础设施与质量体系

这是 RAG 和 HITL 的基础，应优先完善。

本阶段包含：

- Agent Evaluation；
- Observability；
- Guardrails；
- Tool Governance；
- Context Engineering；
- Reliability & Fault Tolerance。

## 4.1 Agent Evaluation：Agent 评估体系

\<badge color="success">核心必做\</badge>

目标：

建立可重复、可量化的评估体系，能够判断 Agent 是否正确理解用户需求、调用工具、使用知识和生成最终回答。

### A. 建立固定评估数据集

创建独立的评估用例，覆盖不同复杂程度的 PC 配置需求。

至少覆盖：

1. 有明确预算和用途的需求。
2. 只有用途、没有预算的需求。
3. 同时包含多个用途的需求。
4. 存在硬件品牌偏好的需求。
5. 存在相互冲突的硬件约束。
6. 用户没有提供足够信息的需求。
7. 需要硬件技术知识解释的问题。
8. 需要 RAG 检索官方文档的问题。
9. 需要工具调用和多步骤协调的问题。
10. 用户在 HITL 暂停后补充需求的问题。

每个用例至少包含：

- 输入；
- 预期结构化需求；
- 关键约束；
- 预期工具行为；
- 预期回答要求；
- 不能发生的错误行为。

评估数据必须与生产用户数据隔离。

未经授权不得直接把用户的敏感对话保存进测试集。

### B. 评估指标

至少评估以下维度：

评估维度

目标

Requirement Parsing

用户需求解析准确性

Constraint Extraction

硬性约束提取准确性

Tool Selection

是否选择正确工具

Tool Arguments

工具参数是否正确

Retrieval Quality

RAG 检索质量

Groundedness

回答是否有证据支持

Citation Correctness

引用是否真实、准确

Answer Quality

最终回答质量

HITL Correctness

是否在正确场景暂停和恢复

Recovery

工具失败后的恢复表现

Latency

端到端耗时

Cost

Token 与模型调用成本

必须区分：

**确定性业务评估与 LLM 质量评估。**

例如：

预算、报价、兼容性、硬件 ID 和 BuildResult 的正确性必须通过确定性断言验证，不能让另一个 LLM 判断 Java 求解器是否正确。

LLM-as-Judge 可以辅助评价解释质量、检索相关性和回答可读性，但不能作为业务正确性的唯一依据。

### C. 回归评估

当以下内容发生变化时，应能够重新运行评估集：

- Prompt；
- 模型；
- RAG；
- Tool；
- Graph；
- Context Engineering；
- HITL；
- 响应生成逻辑。

建立评估报告，记录新版本与基线版本之间的差异。

先测量当前基线，再制定合理的质量阈值。禁止在没有基线数据时自行编造准确率或性能提升目标。

产出：

`docs/pc-config/agent-evaluation.md`

## 4.2 Observability：Agent 可观测性

\<badge color="success">核心必做\</badge>

目标：

可以追踪一次 Agent 任务从开始到结束的完整执行路径。

建议实现 Graph / Node / LLM / Tool / Retrieval / HITL 级别的追踪。

至少记录：

字段

作用

`conversation_id`

关联业务会话

`thread_id`

关联 LangGraph 执行状态

`run_id`

标识一次执行

`node_name`

当前执行节点

`model_name`

实际调用模型

`prompt_version`

Prompt 版本

`tool_name`

调用工具

`latency_ms`

执行耗时

`token_usage`

Token 使用量

`retry_count`

重试次数

`error_type`

错误类型

`retrieval_doc_ids`

RAG 检索文档 ID

`interrupt_status`

HITL 暂停和恢复状态

### 必须实现的追踪能力

1. 一次 Agent 任务可以查看完整节点执行顺序。
2. 可以查看每个节点的耗时。
3. 可以知道调用了哪些模型。
4. 可以查看工具调用参数及执行结果。
5. 可以查看 RAG 命中了哪些文档。
6. 可以查看 HITL 在哪里暂停、用户提供了什么类型的输入、之后是否恢复。
7. 可以区分模型错误、工具错误、业务错误和用户输入问题。
8. 能关联到最终 BuildResult。

### 技术选择

优先评估现有日志系统和 OpenTelemetry。

可以评估 LangSmith 的 Trace 和 Evaluation 能力，但不要默认要求使用付费 SaaS 或将项目绑定到某个特定商业平台。

如果已有可观测系统，应直接复用。

### 隐私和安全

- 不记录 API Key；
- 不记录访问令牌；
- 不将敏感用户信息输出到普通日志；
- 对工具输入和外部响应进行必要脱敏；
- 控制日志保留周期；
- 不因追踪而无限存储完整对话内容。

产出：

`docs/pc-config/agent-observability.md`

## 4.3 Guardrails：Agent 安全护栏

\<badge color="success">核心必做\</badge>

目标：

限制 LLM 和外部知识内容对业务系统造成错误影响。

需要实现以下保护：

### 输入层

- 用户输入结构校验；
- 需求字段类型验证；
- 预算格式验证；
- 不合法硬件 ID 检查；
- 超长输入限制；
- 必要的输入安全处理。

### Prompt 与 RAG 安全

- 将外部文档视为不可信内容；
- 不执行检索文档中出现的系统指令；
- 不允许外部文档覆盖系统 Prompt；
- 防止 Prompt Injection 影响工具权限；
- 检查用户是否尝试诱导 Agent 访问其他用户的数据。

### 工具层

- ToolSpec 白名单；
- 工具参数 Schema 校验；
- 工具权限控制；
- 调用超时；
- 重试次数限制；
- 工具调用上限；
- 明确的错误分类；
- 禁止未经授权的工具调用。

### 输出层

- 验证结构化输出；
- 验证引用是否存在；
- 禁止编造硬件型号；
- 禁止编造价格；
- 禁止编造 Benchmark；
- 禁止把 UNKNOWN 解释成 PASS；
- 禁止把 RAG 文档中的推测写成确定的兼容性结论。

特别要求：

Agent 不得通过任何工具或 Prompt 直接绕过 Java 业务规则。

### 防护原则

不要为了防止 Prompt Injection 而简单拒绝所有包含特殊指令或复杂技术内容的用户输入。

必须区分合法的 PC 硬件问题与真实的越权操作。

产出：

`docs/pc-config/agent-guardrails.md`

## 4.4 Context Engineering：上下文工程

\<badge color="success">核心必做\</badge>

目标：

建立清晰的上下文组织规则，使 Agent 只接收当前任务真正需要的信息。

需要检查并完善：

- System Prompt；
- 用户当前输入；
- 历史消息；
- 结构化需求；
- 用户偏好；
- Java 工具返回结果；
- RAG 检索结果；
- BuildResult；
- 其他节点中间状态。

### 核心要求

1. 保留当前 `PCConfigState` 必要字段和既有兼容性。
2. 不将所有历史消息无限累积到 LLM 上下文。
3. 不重复传递大量硬件目录和报价数据。
4. 使用结构化业务状态，而不是通过自然语言消息传递所有业务参数。
5. 对长历史进行合理摘要。
6. 区分短期会话上下文与长期用户偏好。
7. 控制上下文 Token 预算。
8. 保持工具返回结果和来源信息。
9. RAG 文档内容必须与系统指令隔离。
10. 避免摘要丢失用户的硬性约束。

上下文压缩不得丢失：

- 预算；
- 用户指定的硬件要求；
- 禁止使用的硬件；
- 工作负载；
- 关键兼容性要求；
- 用户已确认的选择。

产出：

`docs/pc-config/context-engineering.md`

## 4.5 Reliability & Fault Tolerance：可靠执行

\<badge color="success">核心必做\</badge>

目标：

保证 Agent 在模型、工具、检索和网络发生异常时，能够明确失败、合理恢复，而不是无限重试或产生错误配置。

实现或完善：

- 节点超时；
- 工具超时；
- 受控重试；
- 错误分类；
- 失败降级；
- 幂等性；
- Graph Checkpoint；
- 任务恢复；
- 用户取消；
- HITL 等待和恢复；
- 并发请求保护。

重试必须具备合理的错误分类。

例如：

- 网络暂时失败可以有限重试；
- 参数错误不能无限重试；
- 业务无可行解不能通过反复调用模型解决；
- 无有效报价不能通过 MOCK 补位；
- 权限失败不能自动绕过。

---

# 五、Stage 11.2：RAG 硬件知识检索体系

\<badge color="success">明确实施\</badge>

这是本阶段的重要业务能力。

## 5.1 RAG 的业务目标

让 Agent 能够检索和解释结构化硬件数据库无法完整表达的技术知识。

首期知识范围：

1. CPU 官方技术规格与产品资料；
2. GPU 官方技术规格与产品资料；
3. 主板用户手册；
4. CPU Support List；
5. BIOS 版本和兼容性说明；
6. 内存 QVL；
7. 散热器安装与平台支持文档；
8. 机箱尺寸与安装限制；
9. 电源接口与供电说明；
10. 其他经过审核的硬件技术文档。

优先采用硬件制造商的官方文档。

第三方文章和社区资料可以作为补充来源，但必须明确标记来源等级。

### 不属于首期 RAG 的数据

以下内容继续使用结构化数据和 Java API：

- 当前商品价格；
- 淘宝和京东 Offer；
- Benchmark 数值；
- 当前硬件候选池；
- 用户预算；
- 当前 BuildSnapshot；
- Java 兼容性计算结果。

RAG 不应该取代这些权威业务数据。

## 5.2 数据采集和文档管理

先设计一个受控的知识文档导入流程。

文档来源可以包括：

- 官方 PDF；
- 官方 HTML 技术资料；
- 官方支持列表；
- 用户明确提供的资料；
- 其他经过来源审核的知识文件。

每份文档必须记录必要元数据：

- `document_id`
- `title`
- `manufacturer`
- `hardware_category`
- `model_name`
- `document_type`
- `source_url`
- `source_type`
- `document_version`
- `published_at`（存在时）
- `retrieved_at`
- `content_hash`
- `language`
- `status`

对于 PDF：

- 尽可能保留页码；
- 尽可能保留表格结构；
- 保留文档标题和章节；
- 不要只提取一整段无结构文本；
- 不能准确解析的图表应标记为未解析，不能猜测内容。

对于 HTML：

- 保留标题、章节和表格上下文；
- 去掉无关导航和广告；
- 保留原始文档链接。

不能只保存清洗后的内容而丢失来源。

## 5.3 RAG 数据处理 Pipeline

建立清晰的处理流程：

```
Document Source
      |
      v
Document Registration
      |
      v
File / HTML Parsing
      |
      v
Content Normalization
      |
      v
Metadata Extraction
      |
      v
Document Chunking
      |
      v
Embedding Generation
      |
      v
Knowledge Index
      |
      v
Retrieval
      |
      v
Evidence / Citation
      |
      v
Agent Response
```

必须支持：

- 文档重复识别；
- 内容 Hash；
- 增量更新；
- 文档失效；
- 文档删除；
- 版本追踪；
- Chunk 来源追溯；
- 失败重试；
- 索引重建。

同一份文档重复导入，不应无限生成重复 Chunk。

## 5.4 Chunking 与 Metadata

不能简单固定每 500 个字符切分所有硬件文档。

需要根据文档结构设计切分策略：

- 标题；
- 章节；
- 表格；
- 参数列表；
- 兼容性说明；
- BIOS 版本说明。

Chunk 必须保留与硬件查询有关的关键上下文。

例如，主板 CPU 支持列表需要保留：

- 主板型号；
- CPU 型号；
- BIOS 版本；
- 备注和支持限制。

不能将表格中的型号和 BIOS 版本切分到不同 Chunk 后造成信息关联丢失。

检索结果必须保留文档和页码信息。

## 5.5 Vector Store 与检索技术选型

不要因为要做 RAG 就直接引入一个全新向量数据库。

先检查：

- 当前 PostgreSQL 能力；
- 是否已经安装 pgvector；
- Agent Service 当前数据存储；
- 是否已有向量存储或检索组件；
- 当前部署环境的运维复杂度。

优先评估复用现有 PostgreSQL 和 Agent 数据库的可行性。

如果采用 pgvector：

- 检查实际 PostgreSQL 版本；
- 检查扩展是否支持；
- 评估索引类型；
- 评估 Embedding 模型；
- 评估数据量和检索性能；
- 控制新增数据库迁移范围。

如果不具备合理条件，再比较其他向量存储方案。

不要默认额外部署 Milvus、Qdrant 或独立搜索微服务。

### 检索方式

根据实际测试评估：

- Dense Vector Retrieval；
- Keyword Retrieval；
- Hybrid Retrieval；
- Metadata Filtering；
- Reranking。

不要在没有数据证明收益的情况下，将所有技术全部叠加。

建议先构建一个小型基准集，比较不同检索策略，再确定首期方案。

## 5.6 RAG Retrieval Tool

将检索能力以受控方式提供给 Agent。

建议提供统一的硬件知识检索工具，具体命名遵循现有 ToolSpec 规范。

输入可以包括：

- 用户问题；
- 硬件类别；
- 品牌；
- 型号；
- 文档类型；
- 检索范围。

输出应包括：

- 文档名称；
- 章节；
- 页码；
- 相关片段；
- 来源链接；
- 文档版本；
- 相关性信息。

Agent 不应该直接访问向量数据库。

### 检索触发策略

不要对每条普通配置请求都执行 RAG。

以下情况优先触发：

- 用户询问具体硬件技术原理；
- 用户询问 BIOS 支持；
- 用户询问主板支持列表；
- 用户询问 QVL；
- 用户询问硬件规格之间的关系；
- 求解结果包含需要技术文档解释的 WARNING / UNKNOWN；
- 用户要求解释某个硬件选择的技术依据。

对于简单配置请求，应优先使用现有结构化数据和 Java Solver，避免无意义的知识检索。

## 5.7 RAG 的权威边界

必须严格区分：

数据

权威来源

硬件型号与标准规格

Java 硬件目录

Benchmark

Java Benchmark Repository

商品与价格

Java OfferRepository

预算

Java

兼容性计算

Java CompatibilityValidator

配置求解

Java BuildSolver

官方技术知识

RAG 检索到的可信原始资料

RAG 检索到一份主板说明书，不能直接修改 Java 兼容性计算结果。

RAG 可以提供证据、解释或发现数据缺口。

如果 RAG 文档与 Java 结构化数据冲突：

1. 不得自行覆盖 Java 数据；
2. 明确展示冲突；
3. 记录来源；
4. 必要时标记待核验；
5. 后续由数据治理流程决定是否更新主数据或兼容性规则。

## 5.8 引用与回答

RAG 生成的技术解释必须具备可追溯引用。

引用至少包含：

- 文档标题；
- 来源；
- 页码或章节；
- 文档版本；
- 原始链接（如有）。

复用现有 `citations` SSE 事件和前端展示能力。

不要为了实现 RAG 而重新设计整个消息协议。

如果现有引用结构不够用，先评估最小兼容扩展。

### RAG 验收

至少覆盖：

1. 正确检索 CPU 官方规格；
2. 正确检索 GPU 官方资料；
3. 正确查询主板 CPU Support List；
4. 正确查询 BIOS 版本资料；
5. 正确查询 QVL；
6. 能处理文档中没有答案的问题；
7. 能识别不同型号相似文档；
8. 能返回页码或章节；
9. 能处理文档版本冲突；
10. 不会把检索文档中的恶意指令当作系统指令；
11. 不会使用 RAG 虚构商品价格；
12. 不会让 RAG 代替 Java 兼容性验证。

产出：

`docs/pc-config/rag-knowledge-system.md`

---

# 六、Stage 11.3：HITL 人机协作能力

\<badge color="success">明确实施\</badge>

## 6.1 HITL 的目标

让 Agent 能够在必要时暂停任务，等待用户提供信息或确认，然后从正确的执行位置恢复。

HITL 不应只是一条普通的追问消息。

必须具备：

- Graph 暂停；
- 状态持久化；
- 等待用户输入；
- 输入校验；
- 使用原有执行状态恢复；
- 任务取消；
- 恢复失败处理。

## 6.2 首期 HITL 适用场景

### A. 需求澄清

例如：

用户说：

> 我要一台适合开发和 AI 的电脑。

但没有说明 AI 是云端使用，还是本地运行模型。

如果这会明显改变 GPU 显存和预算分配，应暂停并询问。

其他例子：

- 预算缺失或含义不明确；
- 关键用途存在歧义；
- 两个硬性需求发生冲突；
- 必须知道的硬件约束缺失；
- CPU 渲染与 GPU 渲染无法区分。

现有 requirement_parser 的澄清分支应继续复用。

普通澄清与真正的 Graph 中断需要区分，避免把所有追问都做成复杂的 HITL 机制。

### B. 重要假设确认

如果 Agent 对用户需求进行了可能明显影响配置结果的推断，可以让用户确认。

例如：

- 默认将本地 AI 推理作为主要用途；
- 用户提出的某项偏好与预算明显冲突；
- 用户需要在更高性能和更低预算之间作选择。

### C. 不确定技术结果确认

如果关键技术数据存在 UNKNOWN 或 WARNING：

- 向用户解释不确定性；
- 展示已有证据；
- 在必要时请求补充信息；
- 不允许用户的确认直接把 UNKNOWN 改成 PASS；
- 未通过 Java 规则验证的配置不能标记为完全兼容。

### D. 高影响操作

当前产品不涉及自动购物、支付和硬件自动修改。

不得为了实现 HITL 而虚构购买审批流程。

未来如果新增会实际产生外部影响的操作，再单独增加相应确认机制。

## 6.3 LangGraph 持久化与 Interrupt

必须检查当前 LangGraph Checkpointer 实现。

如果已有 PostgreSQL Checkpointer，应优先复用。

如果没有，需要在现有 Agent PostgreSQL 存储边界内评估并建立可靠持久化能力。

禁止直接使用仅存在于 Python 进程内存的状态作为生产 HITL 持久化方案。

需要支持：

1. 在明确节点暂停；
2. 保存 Graph State；
3. 保存当前 `thread_id`；
4. 返回结构化待处理问题；
5. 用户提交答案；
6. 对答案进行校验；
7. 使用原来的 `thread_id` 恢复；
8. 继续执行剩余节点；
9. 最终生成正常 BuildResult。

使用当前安装版本支持的 LangGraph `interrupt` 和 resume 机制，不能照搬不匹配当前版本的示例代码。

参考官方机制：

- `interrupt()`；
- `Command(resume=...)`；
- Persistent Checkpointer；
- 同一 thread_id 恢复。

官方文档：\
<https://docs.langchain.com/oss/python/langgraph/interrupts>

### 特别注意 LangGraph 的恢复语义

恢复时，中断所在节点可能从节点入口重新执行，而不是从中断语句之后继续运行。

因此：

- 中断前的副作用操作必须设计为幂等；
- 不要在 interrupt 前重复写入业务数据；
- 每个中断节点的逻辑必须可安全重放；
- 正确使用持久化状态；
- 避免在一个节点内部使用循环反复调用 interrupt；
- 对用户输入做明确 Schema 校验。

## 6.4 HITL API 与 SSE

需要检查当前 Agent API 和 SSE 契约。

目前前端已经使用现有消息和 SSE 事件消费机制。

必须保证：

- HITL 暂停状态可以被前端识别；
- 可以展示待回答的问题；
- 可以展示必要的选项或输入字段；
- 用户提交答案后可以恢复原 Graph；
- 恢复操作不会新建一个无关的 thread；
- 重复提交不会重复执行同一恢复操作；
- 用户不能恢复其他用户的任务；
- 用户无法通过猜测 thread_id 越权访问执行状态。

优先扩展现有契约。

不能为了 HITL 直接替换整个 SSE 系统。

如果必须增加新的事件或 API 字段：

1. 说明为什么现有契约无法表达；
2. 保持向后兼容；
3. 同步 Java、Agent 和 Frontend；
4. 更新接口文档；
5. 增加完整测试。

待处理交互至少应能表达：

- `interrupt_id` 或等效标识；
- `interaction_type`；
- `question`；
- `input_schema` 或可选项；
- 必要的上下文摘要；
- 当前交互状态。

不要把整个内部 LangGraph State 暴露给前端。

## 6.5 HITL 权限与状态保护

必须实现：

- 当前用户只能恢复自己的会话；
- 服务端验证 thread 和 user 的关联关系；
- 同一个中断不能被并发重复恢复；
- 无效输入不能继续执行；
- 用户主动取消后不再继续；
- 长期未处理的中断可以进入过期或待恢复状态；
- 任务异常时能明确显示失败原因。

如果需要新的业务持久化记录，先评估现有 Java 会话管理和 Agent Checkpointer，避免建立两套相互矛盾的状态权威。

### HITL 验收

至少测试：

1. 正常澄清并恢复；
2. 输入错误后重新询问；
3. 用户中途退出后重新打开会话；
4. Agent Service 重启后恢复；
5. 同一个中断重复提交；
6. 不同用户尝试恢复其他 thread；
7. 用户取消任务；
8. 中断超时或过期；
9. 恢复节点出现异常；
10. 恢复后能够正常生成 BuildResult；
11. 原有无 HITL 的配置请求不受影响。

产出：

`docs/pc-config/hitl-workflow.md`

---

# 七、Stage 11.4：Memory 与用户偏好——评估优先，不强制建设完整长期记忆系统

\<badge color="info">可选扩展\</badge>

需要明确区分以下概念：

能力

作用

Checkpointer

当前线程执行状态和会话上下文

Memory

跨会话保留用户偏好和事实

RAG

检索外部硬件技术知识

BuildSnapshot

历史配置与当时使用的数据

不要把四者混在一起。

### 首期 Memory 评估范围

评估用户是否需要保存：

- CPU 品牌偏好；
- GPU 品牌偏好；
- 预算习惯；
- 使用场景；
- 是否重视性价比；
- 是否偏好小机箱；
- 是否喜欢 RGB；
- 对噪音、体积和功耗的偏好。

### 实施原则

1. 用户明确提供的长期偏好才有保存价值。
2. 临时预算不能自动变成长期偏好。
3. 用户有权查看、更新和删除偏好。
4. 保存偏好应遵循用户的明确选择。
5. 不应将整段历史对话无差别存入长期 Memory。
6. 用户历史配置应优先使用已有 BuildSnapshot。
7. 不允许将 Agent Memory 变成第二套用户资料数据库。

### 权威边界

Java Application Service 继续作为用户业务资料的权威。

如果已经存在用户偏好和个人资料 API，应优先复用。

不应为了 LangGraph Memory 直接创建一套重复的用户偏好数据库。

LangGraph Store 可以作为技术实现候选，但必须先分析它与现有 Java 用户数据体系的关系。

本阶段输出：

- Memory 适用场景；
- 记忆分类；
- 数据所有权；
- 用户授权与管理方式；
- 是否值得立即实现；
- 后续实施条件。

如果没有充分必要性，允许得出“暂缓实现”的结论。

产出：

`docs/pc-config/agent-memory-strategy.md`

---

# 八、Stage 11.5：MCP 可行性评估——暂不预设实施

\<badge color="warning">只做架构决策评估\</badge>

本项目目前已经具备：

- Java 内部 HTTP API；
- Agent ToolSpec；
- Python 工具执行；
- 服务鉴权；
- 明确的 Java 和 Agent 服务边界。

因此，MCP 不应该被视为当前 Agent 必须使用的通信协议。

请分析以下场景是否真实存在：

1. 多个独立外部硬件数据服务需要统一接入；
2. 多个 Agent 客户端需要复用同一套工具；
3. 外部数据服务已经提供 MCP Server；
4. 需要通过协议实现动态工具发现；
5. 当前 ToolSpec 的能力已无法合理满足外部工具互操作。

必须区分：

- Agent 作为 MCP Client，使用外部 MCP Server；
- 本项目作为 MCP Server，向外部 AI 客户端提供工具。

这两种方向不是同一件事。

### 如果当前没有真实需求

明确记录：

- 当前为什么不需要 MCP；
- 现有 HTTP API 与 ToolSpec 如何满足需求；
- 什么条件出现后值得重新评估；
- 引入 MCP 会增加什么运维、权限和安全成本。

不必为了 Stage 11 完整而强行安装 MCP 依赖。

产出：

`docs/pc-config/adr-mcp-adoption.md`

结论可以是 `DEFERRED`，不要求实现。

---

# 九、Stage 11.6：Multi-Agent 可行性评估——不预设实施

\<badge color="warning">只做架构决策评估\</badge>

当前核心 PC 配置流程已经采用确定性 Graph 和 Java Solver。

Multi-Agent 只有在多个任务具有相对独立的职责、适合并行研究或确实需要独立 Agent 上下文时才有价值。

请评估：

### 潜在使用场景 A：复杂硬件技术研究

多个 Agent 并行研究：

- CPU；
- GPU；
- 主板与 BIOS；
- AI 推理需求。

最后交给一个协调节点汇总证据。

### 潜在使用场景 B：复杂硬件升级研究

分别研究：

- CPU 升级条件；
- GPU 升级条件；
- 供电要求；
- 机箱空间；
- 预算与替换影响。

最终仍由 Java 验证整机兼容性。

### 潜在使用场景 C：多个外部知识源的并行研究

不同 Agent 研究不同厂商文档或资料来源，汇总结果后再交给 RAG 或业务系统。

### 必须评估的成本

- 模型调用次数；
- Token 成本；
- 任务协调；
- 上下文传递；
- 状态管理；
- 并行任务失败；
- 最终结果冲突；
- 调试复杂度；
- 延迟增加。

特别要求：

**禁止将 CPU Agent、GPU Agent、主板 Agent 等局部推荐结果直接拼接成整机配置。**

硬件组合属于全局约束优化问题，最终选择仍必须通过 Java BuildSolver。

### 决策原则

只有在单 Graph 明确存在任务拆分、并行执行或专业上下文隔离需求，并能通过固定测试证明收益时，才建议引入 Multi-Agent。

如果单 Graph 已经足够，明确记录暂不引入的原因。

不要求本阶段实际重写成 Multi-Agent。

产出：

`docs/pc-config/adr-multi-agent-adoption.md`

---

# 十、Stage 11.7：完整 Agent 集成与质量验收

完成核心能力后，进行完整验证。

## 10.1 RAG + Agent

验证：

- 用户提出专业硬件问题；
- Agent 正确识别需要检索；
- 检索得到可信文档；
- 文档内容正确进入上下文；
- 生成回答时带有有效引用；
- 检索失败时能明确告知用户；
- 不会编造文档页码或内容；
- 不会绕过 Java 兼容性判断。

## 10.2 HITL + Agent

验证：

- 用户提出模糊需求；
- Agent 能识别缺失约束；
- Graph 暂停；
- 状态持久化；
- 前端展示待回答问题；
- 用户提交答案；
- Graph 使用原 thread 恢复；
- 最终产生正常 BuildResult。

## 10.3 Evaluation

将 RAG 和 HITL 场景加入固定评估集。

测试：

- 需求解析；
- 检索质量；
- 引用质量；
- 交互正确性；
- 状态恢复；
- 工具调用；
- 最终回答质量。

## 10.4 Guardrails

测试：

- Prompt Injection；
- 恶意外部文档；
- 无效硬件 ID；
- 错误工具参数；
- 非法用户恢复请求；
- 越权访问；
- 无效结构化输出；
- 伪造报价或 Benchmark；
- 无限制的重复工具调用。

## 10.5 整体系统回归

必须确认：

- 原有 PC Graph 主流程正常；
- 现有 ToolSpec 正常；
- Java 内部 API 正常；
- SSE 正常；
- 现有引用展示正常；
- BuildResult 正常；
- BuildSnapshot 正常；
- OpenUI 集成不受影响；
- 无 HITL 请求仍然能够顺利完成；
- Agent Service 重启后，持久化的 HITL 状态可正确恢复。

Stage 9 正在积累的真实报价数据不能被测试或重置操作破坏。

不允许使用 MOCK 数据证明生产可信报价链路通过。

---

# 十一、技术与依赖选型原则

本阶段必须以当前仓库中的实际版本为依据。

不要直接照抄网络上最新版本的 LangGraph 或 LangChain 代码。

实施前检查：

- Python 版本；
- LangChain 版本；
- LangGraph 版本；
- Embedding 模型；
- LiteLLM 配置；
- PostgreSQL 版本；
- 当前 Checkpointer；
- 现有 SSE 实现；
- 前端依赖。

涉及 LangGraph interrupt、resume、Checkpointer、Retriever API 等能力时，必须查阅与当前安装版本匹配的官方文档。

可参考：

- LangGraph Interrupts：<https://docs.langchain.com/oss/python/langgraph/interrupts>
- LangGraph Persistence：<https://docs.langchain.com/oss/python/langgraph/persistence>
- LangChain Retrieval：<https://docs.langchain.com/oss/python/langchain/retrieval>
- LangSmith Evaluation：<https://docs.smith.langchain.com/evaluation>

不要为了使用新框架盲目升级现有稳定依赖。

### 向量存储原则

优先复用现有 Agent PostgreSQL 存储，并评估 pgvector。

不能直接使用 Java 业务数据库作为 RAG 知识库。

不新增独立向量数据库，除非现有能力经评估确实无法满足要求。

### 可观测性原则

优先评估现有日志和 OpenTelemetry。

不要默认引入必须依赖商业 SaaS 的架构。

### 工具治理原则

继续使用现有 ToolSpec。

不得为了 RAG、MCP 或 Multi-Agent 另建相互冲突的工具权限体系。

---

# 十二、Stage 11 实施顺序

请按下面顺序实施：

阶段

主要任务

交付性质

11.0

现有 Agent 基线审计

必须

11.1

Evaluation、Observability、Guardrails、Context Engineering、可靠性

必须

11.2

RAG 知识检索体系

必须

11.3

HITL 人机协作

必须

11.4

Memory 长期记忆评估

评估为主

11.5

MCP 可行性评估

评估为主

11.6

Multi-Agent 可行性评估

评估为主

11.7

完整集成与质量验收

必须

阶段之间允许在不破坏依赖关系的情况下并行开发。

但 RAG 和 HITL 的基础设施必须先经过架构审计。

不能为了赶进度跳过持久化、权限控制和评估体系。

---

# 十三、工程实施要求

## 13.1 Git 和工作区保护

开始工作前检查：

- 当前分支；
- HEAD；
- `git status`；
- 未提交修改；
- 未跟踪文件；
- 当前 Stage 9 的数据变更；
- 当前 Stage 10 的实施状态。

不要假设当前代码等于历史实施报告中的基线。

严禁：

- git reset；
- git clean；
- 覆盖用户文件；
- 擅自 stash；
- 删除未知来源的文件；
- 清理 Stage 9 采集结果；
- 覆盖 `offers.json`。

如果存在冲突，先识别归属，不要直接修改。

## 13.2 控制修改范围

优先修改：

- Agent Service；
- 必要的 Agent API；
- 必要的 React 交互组件；
- Agent 数据库中的必要结构；
- 对应的文档和测试。

Java 只在确实需要读取用户偏好、会话权限或提供必要接口时进行最小调整。

不得为了 HITL 或 RAG 把 Java 业务职责转移给 Python。

不得创建新的微服务。

## 13.3 阶段验收

每个子阶段完成后都必须：

1. 运行对应单元测试；
2. 运行类型和静态检查；
3. 执行必要的集成测试；
4. 更新相关文档；
5. 记录实际修改文件；
6. 说明未完成事项；
7. 明确下一个阶段的依赖。

测试失败时不能伪装成通过。

如果需要第三方 API 凭证、模型权限或真实官方资料才能完成某项能力，应先完成不依赖该条件的代码与测试，并明确记录剩余阻塞，不能使用虚构数据宣称完成。

---

# 十四、明确不属于 Stage 11 的工作

以下内容不属于本阶段：

- 重写 Java BuildSolver；
- 重写 CompatibilityValidator；
- 修改 Stage 8 硬件主数据治理规则；
- 重做 Stage 9 商品采集；
- 修改正在采集的 `offers.json` 数据；
- 新增 Marketplace 微服务；
- 新建多套用户资料数据库；
- 全面重构 Agent Graph；
- 强制将 Agent 转换为 Multi-Agent；
- 强制让所有 Java API 通过 MCP 调用；
- 新增不必要的微服务或消息队列；
- 智能配置对比；
- 硬件替换；
- 性能瓶颈分析；
- 自动购物或购买审批；
- 完整商业化运营后台。

上述高级产品功能留在后续 Stage 12。

---

# 十五、文档交付要求

优先更新现有文档，避免创建重复内容。

至少维护以下文档：

文档

内容

`stage-11-readiness-report.md`

初始代码与能力审计

`agent-evaluation.md`

评估数据集、指标、基线和回归策略

`agent-observability.md`

Graph、模型、工具、RAG 和 HITL 追踪

`agent-guardrails.md`

输入、Prompt、工具、检索和输出安全

`context-engineering.md`

State、消息、上下文组装和压缩策略

`rag-knowledge-system.md`

文档来源、索引、检索、引用和数据管理

`hitl-workflow.md`

中断、用户交互、恢复和权限管理

`agent-memory-strategy.md`

长期记忆和用户偏好方案

`adr-mcp-adoption.md`

MCP 是否采用的决策记录

`adr-multi-agent-adoption.md`

Multi-Agent 是否采用的决策记录

`pc-config-stage-11-report.md`

最终实施报告

如果这些内容已经存在于现有文档中，直接更新原文档。

不要为了完成清单而机械创建重复文件。

---

# 十六、Stage 11 最终验收标准

Stage 11 完成时必须达到：

### RAG

- 具有可维护的硬件技术文档知识库；
- 能根据用户问题检索相关文档；
- 能保留来源、章节和页码；
- 能提供可验证的引用；
- 能处理无结果和文档冲突；
- 不会取代 Java 业务数据权威。

### HITL

- 支持必要的用户澄清和确认；
- 能够暂停 Graph；
- 状态持久化；
- 能够恢复原有执行线程；
- 有权限验证；
- 有输入校验；
- 有取消与错误处理；
- 不影响正常无中断流程。

### Evaluation

- 有固定测试数据集；
- 有结构化需求和工具调用评估；
- 有 RAG 检索评估；
- 有 HITL 恢复评估；
- 能执行回归；
- 能比较不同版本表现。

### Observability

- 能追踪整个 Graph；
- 能查看节点耗时；
- 能查看模型与工具调用；
- 能查看检索和引用；
- 能查看 HITL 状态转换；
- 敏感数据不会泄漏到日志。

### Guardrails

- 输入和输出经过验证；
- 工具权限受控；
- 检索文档视为不可信数据；
- 防止 Prompt Injection 影响工具执行；
- 不允许 Agent 绕过 Java 的业务决策。

### Context Engineering

- 上下文有明确结构；
- 长对话能够合理压缩；
- 不丢失用户硬性要求；
- 短期会话和长期偏好边界清楚；
- 不产生重复、无效的上下文输入。

### Memory

- 已完成是否值得引入的评估；
- 明确与 Java 用户资料和 BuildSnapshot 的关系；
- 未经决定，不强制建设完整长期记忆系统。

### MCP 与 Multi-Agent

- 已完成适用场景分析；
- 有明确的采用或暂缓结论；
- 暂缓时说明重新评估条件；
- 不为了使用技术而引入复杂度。

---

# 十七、最终执行原则

请始终遵守以下优先级：

1. 业务正确性；
2. 数据可信度；
3. 用户交互可靠性；
4. Agent 可追踪与可评估；
5. 知识检索质量；
6. 执行效率；
7. 架构扩展性；
8. 技术先进性。

不要因为某个功能可以通过 LLM 实现，就将其全部交给 LLM。

不要因为 MCP、Multi-Agent、Memory 等技术很流行，就默认它们必须进入项目。

不要让 RAG 的检索结果取代 Java 的结构化数据和确定性规则。

不要让 HITL 成为一套独立于现有会话系统的复杂任务管理平台。

不要让 Evaluation 只剩下几条简单的 Prompt 测试。

**最终目标：使 PC 配置 Agent 具备可信的硬件知识检索能力、可靠的人机协作能力、可验证的执行质量和可控的工具使用能力，同时维持现有确定性 PC 配置业务架构。**

现在开始 Stage 11.0 审计，并按照 11.1–11.7 的顺序分阶段完成实施。不要只输出理论方案。遇到真实阻塞时明确记录原因，并继续完成不依赖该阻塞的任务。
