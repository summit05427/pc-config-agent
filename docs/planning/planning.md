# 项目任务：基于现有 Agent 应用模板开发 PC 配置智能推荐 Agent Demo

## 0. 任务定位

基于当前 Monorepo Agent 应用模板，进行增量式业务开发，交付一个可运行、可演示、具有后续扩展基础的：

**基于 LLM 的 PC 配置智能推荐 Agent 应用。**

本次开发时间约束为 3 天。

开发者使用 AI Coding Agent 完成代码实现，因此应优先保证完整业务链路、模块边界、代码质量、项目文档和未来可扩展性。

不要按照固定日历日期拆分工作。

应当根据工作依赖关系，将任务组织为若干连续交付阶段。允许并行处理互不依赖的任务，但不得在核心依赖尚未完成时盲目开发上层功能。

本次目标不是完整生产版本，而是一个经过实际测试的端到端 Demo。

同时，必须保证未来增加数据治理、商品管理、配置对比、性能瓶颈分析、硬件替换、RAG、HITL 等能力时，不需要推翻本次建立的核心架构。

***

# 1. 开始之前：必须理解现有工程

在修改任何代码之前，先检查当前真实仓库。

重点阅读：

- `docs/architecture-overview.md`
- `docs/api-contract.md`
- `docs/api-contract-quick-reference.md`
- `docs/model-runtime-architecture.md`
- `docs/services/application-service/architecture.md`
- `docs/services/agent-service/architecture.md`
- `docs/services/agent-service/agent-workflows.md`
- `docs/services/frontend/architecture.md`
- `docs/services/frontend/generative-ui.md`
- `docs/deployment/environment-variables.md`
- `docs/planning/closure-plan.md`
- `.trae/rules/00-monorepo-common.md`
- 相关按需开发规则

阅读与以下内容有关的实际源代码：

1. Agent Profile 解析与注册机制。
2. LangGraph 图装配入口。
3. AgentState 定义。
4. ToolSpec 定义和工具注册机制。
5. Java Internal API 客户端。
6. Agent 模型解析和 Runtime Resolver。
7. SSE 编码和流式消息处理。
8. 前端聊天提交与 SSE 消费。
9. OpenUI 渲染入口。
10. Java Spring Modulith 模块依赖。
11. 现有数据库迁移及 Mapper。
12. 当前测试和评测组织方式。

必须先完成真实代码结构分析。

禁止仅根据项目说明文档推断某个函数、类、接口或配置一定存在。

## 1.1 仓库基线保护

开始前：

- 检查 `git status`。
- 记录当前 HEAD。
- 记录未提交修改。
- 不覆盖用户已有修改。
- 在独立功能分支上工作。
- 不修改与本任务无关的文件。

如果现有工作区存在未提交修改，不得擅自清理或覆盖。

## 1.2 输出初始检查结果

先整理：

- 当前四端架构。
- Agent 工作流现状。
- 可以直接复用的能力。
- 需要新增的能力。
- 预计修改的文件范围。
- 可能存在的接口或架构冲突。
- 三天范围内的实施优先级。

不要为了完成分析而大规模重构。

发现现有模板与本文设计不一致时，以真实代码和项目权威文档为依据，选择最小变更方案，并记录差异及理由。

完成检查后继续执行，不需要因非关键设计选择反复等待用户确认。

***

# 2. 产品需求与功能边界

## 2.1 核心用户需求

用户通过自然语言输入电脑配置需求。

输入可能包含：

- 总预算；
- 使用场景；
- CPU / GPU 品牌偏好；
- 游戏分辨率；
- 目标 FPS；
- 视频剪辑、编程开发、3D 渲染等用途；
- 内存及存储要求；
- RGB 偏好；
- 散热和静音要求；
- 未来升级需求。

预算可以存在，也可以不存在。

## 2.2 输出要求

每一次成功推荐必须完整包含以下八类硬件：

1. CPU
2. GPU
3. Motherboard
4. Memory
5. Storage
6. CPU Cooler
7. Case
8. PSU

每一件硬件至少输出：

- 标准型号；
- 品牌；
- 关键硬件参数；
- 商品标题；
- 商品来源平台；
- 商家；
- 当前核验报价；
- 购买链接；
- 报价核验时间；
- 对应跑分（适用时）；
- 推荐理由。

整个配置还需要输出：

- 用户需求总结；
- 性能分配说明；
- 八件硬件总价；
- 预算校验；
- 兼容性检查；
- 数据完整性提示；
- 商品价格免责声明。

## 2.3 严格预算原则

只要用户给出了预算，就将其视为严格的最高金额约束。

例如：

用户预算 8000 元：

最终配置价格必须满足：

`total_price_fen <= budget_max_fen`

所有货币金额使用整数分，禁止使用浮点金额计算。

不能因为用户说「8000 元左右」就擅自允许超过 8000 元。

优惠券、会员价、附加条件优惠必须明确分类，不允许默认作为所有用户都能获得的价格。

如果找不到满足预算的完整方案，必须返回无可行方案，并说明主要冲突。

禁止偷偷移除某个硬件、使用虚构价格或选择其他型号来伪造满足预算的结果。

没有预算时，不将其理解为无限预算。

采用符合使用场景的性能与价格平衡策略，并向用户说明没有启用硬预算约束。

***

# 3. 总体架构约束

必须保留现有四端架构：

- Frontend
- Admin
- Java Application Service
- Python Agent Service

继续使用现有 PostgreSQL、Redis、LiteLLM 和其他基础设施。

## 3.1 职责边界

### Java Application Service

作为 PC 配置业务数据权威，负责：

- 硬件主数据查询；
- PassMark 数据查询；
- 商品映射；
- 商品报价；
- 兼容性基础校验；
- 配置组合求解；
- 最终预算校验；
- 配置结果快照。

### Python Agent Service

负责：

- 用户意图理解；
- 需求结构化提取；
- PC 配置工作流；
- 工具调用编排；
- 失败处理；
- 推荐解释；
- SSE 输出。

Agent 不得直接访问 Java 业务数据库。

通过现有 `/internal/v1/**` 内部 API 调用 Java。

### Frontend

负责：

- 自然语言需求输入；
- 选择 PC Config Profile；
- SSE 消费；
- 配置结果展示；
- 商品购买链接展示；
- 价格与兼容性信息展示。

不得重做现有全局聊天架构。

### Admin

本次不要求实现完整硬件管理后台。

如果现有管理端无需修改即可支持本次 Demo，则保持不变。

商品管理、审核管理和数据清洗后台放入未来规划。

## 3.2 现有功能保护

禁止无必要地修改：

- Identity；
- Authentication；
- Refresh Token；
- Model Runtime；
- BYOK；
- Usage Ledger；
- 通用会话管理；
- 原有 ReAct Graph；
- 已有 SSE 事件语义；
- 现有前端全局布局；
- 现有管理后台公共组件。

新增业务优先在独立模块中完成。

不允许为了方便直接把 PC 业务代码混入 Identity 或 Model 模块。

***

# 4. PC 业务数据设计

## 4.1 原始硬件数据

当前已有：

- PCPartPicker 约 8300 款硬件；
- PassMark 约 23945 条数据。

本次不要求清洗全部 8300 款数据。

必须保留原始数据，不允许覆盖或删除。

先通过独立脚本进行统计和筛选，选择约 19–30 款能够支持 Demo 的候选硬件。

八个类别必须均有候选数据。

CPU、GPU、主板优先准备多个备选型号。

## 4.2 数据分类

按照以下结构设计数据：

### Hardware

表示标准硬件实体。

主要字段：

- hardware\_id
- category
- brand
- model\_name
- manufacturer\_part\_number
- aliases
- specifications
- data\_quality\_status
- lifecycle\_status
- recommendation\_status
- source
- source\_version

### Benchmark

表示硬件性能记录。

主要字段：

- hardware\_id
- benchmark\_type
- score
- source
- benchmark\_version
- collected\_at
- match\_method
- match\_confidence

### Marketplace Offer

表示某个标准硬件在中国市场对应的实际销售商品。

主要字段：

- offer\_id
- hardware\_id
- platform
- platform\_sku
- seller
- title
- price\_fen
- price\_type
- shipping\_status
- purchase\_url
- match\_status
- offer\_status
- verified\_at
- valid\_until

所有商品均必须经过人工核验。

不允许将相似型号直接认为是同一个商品。

## 4.3 商品数据策略

本次使用人工维护的 Demo 商品集。

管理人员可以从实际商品页面核验信息后录入商品标题、URL、价格、商家及商品 ID。

本次不开发：

- 全网爬虫；
- 全自动 SKU 搜索；
- 商业商品数据供应商集成；
- 复杂联盟推广系统。

商品数据应当通过独立 Repository 或 Provider 接口访问。

未来可以从人工 JSON / CSV 数据升级至 PostgreSQL 商品数据库和自动化匹配服务，而不改变 Agent 工具契约。

## 4.4 商品进入最终推荐的条件

商品必须满足：

- 标准硬件映射已 VERIFIED；
- 商品 URL 已人工核验；
- 商品报价状态有效；
- 未被管理员禁用；
- 关键型号及规格匹配。

对于过期商品、未知库存和报价失效，不得直接作为严格预算计算依据。

如果没有有效报价，则寻找替代商品或硬件；不能猜测价格。

***

# 5. Java PC 配置业务模块

在现有 Spring Modulith 架构中新增独立 PC 业务模块。

模块名称可结合当前项目命名规范确定，例如：

`pcbuild`

建议职责：

- HardwareCatalogService
- BenchmarkQueryService
- OfferQueryService
- BuildSolver
- CompatibilityValidator
- BuildSnapshotService

不要在本次将所有职责拆成大量微小 Spring Modulith 模块。

只有出现清晰独立的领域边界后，才进一步拆分 catalog、commerce、recommendation 等模块。

## 5.1 Repository 抽象

建立适当的数据访问边界，例如：

- HardwareCatalogRepository
- BenchmarkRepository
- OfferRepository
- BuildRepository

三天 Demo 可以采用 JSON / CSV Fixture 实现，但上层 Service 不应直接读取硬编码 JSON 文件。

不要把所有业务逻辑写进 Controller。

未来切换 PostgreSQL 时，应能够替换 Repository 实现，而不需要重写 Agent 或 Solver 调用逻辑。

## 5.2 内部接口

根据现有 API 风格实现最小接口集：

- GET `/internal/v1/pc/hardware/candidates`
- GET `/internal/v1/pc/hardware/{hardwareId}`
- GET `/internal/v1/pc/benchmarks`
- GET `/internal/v1/pc/offers`
- POST `/internal/v1/pc/builds/solve`
- POST `/internal/v1/pc/builds/validate`
- POST `/internal/v1/pc/builds/snapshots`

如认为其中部分接口可以合并，应保持职责清晰并记录设计决定。

所有接口延续现有服务间认证方式。

Agent 使用服务令牌，并在涉及用户归属与用户权限的调用中使用现有 `X-User-Token` 机制。

不得新增第二套认证体系。

## 5.3 Build Snapshot

必须从第一版定义统一配置结果结构。

建议包含：

- build\_id
- user\_id
- parent\_build\_id（可为空）
- requirements\_snapshot
- components
- total\_price\_fen
- budget\_max\_fen
- compatibility\_report
- benchmark\_snapshot
- offer\_snapshot
- solver\_version
- compatibility\_rule\_version
- catalog\_version
- created\_at

优先使用最小的追加式数据库迁移实现持久化快照。

不要仅依赖对话文本保存最终配置。

已有配置不得因为未来商品价格更新而改变历史快照。

未来对硬件进行替换时，创建新版本或新 Build，保留旧配置，不直接覆盖历史记录。

***

# 6. 配置求解器设计

## 6.1 基础方案

本次不强制引入 OR-Tools。

先利用约 19–30 款候选硬件建立有限规模确定性搜索。

不允许在业务代码中使用 LLM 生成随机硬件组合。

## 6.2 硬约束与软目标分离

硬约束包括：

- 八个类别必须齐全；
- 每类恰好一个硬件；
- 严格预算；
- 已知兼容性；
- 商品映射 VERIFIED；
- 报价有效；
- 用户明确要求必须满足的硬性条件。

软目标包括：

- 场景性能；
- 性能与价格平衡；
- 品牌偏好；
- 静音；
- 外观；
- 升级空间；
- 功耗及散热表现。

用户说“必须使用 AMD CPU”时应作为硬约束。

用户说“AMD CPU 优先”时可作为软偏好。

由 Requirement Parser 将其转换为结构化字段。

## 6.3 场景评分

至少支持：

- gaming
- video\_editing
- programming
- workstation
- general\_use

初始权重应放在可配置策略中，而不是写死在 Prompt。

PassMark 数据只是性能代理指标。

不得把 CPU Mark、G3D Mark 直接声称为实际游戏 FPS 或专业应用测试结果。

缺少某项性能数据时，应明确说明，不得让 LLM 自行补分。

## 6.4 兼容性检查

必须至少覆盖：

- CPU / Motherboard Socket；
- 主板 / 内存 DDR 类型；
- 主板 / 机箱板型；
- GPU / 机箱显卡长度；
- Cooler / CPU Socket；
- Cooler / Case 最大散热器高度；
- GPU / PSU 功率与供电接口；
- Storage / Motherboard 接口。

兼容性状态应区分：

- PASS
- WARNING
- FAIL
- UNKNOWN

FAIL 不允许进入最终成功方案。

UNKNOWN 不能伪装成 PASS。

缺少关键参数时，明确标记未验证，并根据该硬件限制决定是否需要排除。

## 6.5 求解算法

先执行候选过滤，再组合。

避免直接对全部硬件执行笛卡尔积。

对组合进行兼容性剪枝、预算剪枝和场景得分计算。

对于同样满足硬约束的方案，返回综合评分最高的配置。

无预算时采用性能与价格平衡策略。

预算不足时返回明确无解结果，不允许擅自放宽预算。

所有金额以分为单位。

***

# 7. Python LangGraph Agent 设计

这是本次最重要的实现部分。

必须将 PC 配置业务设计为独立 LangGraph 工作流。

## 7.1 工作流边界

保留现有通用 ReAct Graph。

新增 PC Configuration Graph。

通过现有 Profile / Workflow 装配入口接入。

优先增加：

`agent_id = pc-config`

具体方式以现有代码为准。

特别注意：如果现有 Profile 只负责 Prompt、Tools、Model 参数，而不具备选择 Graph 的能力，不得假定它能直接完成工作流分流。

应在现有 Graph 装配点实现最小 Workflow Dispatcher。

禁止为了接入 PC Graph 重写整个聊天请求入口、SSE 层或通用 ReAct 图。

## 7.2 Graph 节点结构

建议：

START\
→ requirement\_parser\
→ requirement\_validator\
→ candidate\_retriever\
→ build\_solver\
→ build\_validator\
→ response\_generator\
→ END

失败路径：

- Requirement Invalid → Clarification Response。
- Candidate Empty → No Candidate Response。
- Solver Infeasible → No Solution Response。
- Validation Failed → Limited Re-solve。
- Upstream Unavailable → Safe Error Response。

所有循环必须有次数上限。

不能出现无限重新搜索、无限求解或无限调用模型的情况。

## 7.3 节点详细职责

### requirement\_parser

使用 LLM Structured Output。

输入：用户自然语言。

输出：

- budget\_max\_fen
- budget\_currency
- primary\_usage
- secondary\_usage
- target\_resolution
- target\_fps
- cpu\_brand\_preference
- gpu\_brand\_preference
- hard\_constraints
- soft\_preferences
- appearance\_preferences
- product\_condition
- other\_requirements

不得在此节点查询或编造具体商品。

不得将用户偏好和硬性约束混为一谈。

必须使用 Pydantic Schema 进行结构化验证。

### requirement\_validator

纯代码节点。

检查：

- 预算是否有效；
- 使用场景是否有效；
- 参数是否超出允许范围；
- 硬约束是否冲突；
- 是否缺少必要信息。

缺少关键信息时生成明确追问。

Demo 可以采用用户补充后重新提交需求的简单交互模式。

不要为本次 Demo 引入复杂的 interrupt/resume 实现。

### candidate\_retriever

通过 Java API 查询候选硬件。

查询条件应当根据结构化需求建立。

不要将完整硬件数据库交给 LLM。

返回 candidate\_pool\_id 和必要的摘要。

### build\_solver

调用 Java 确定性求解服务。

Agent 不自行选择最终八个 SKU。

返回 build\_id 和方案摘要。

### build\_validator

独立调用 Java 最终验证服务。

检查：

- 八类别完整性；
- 兼容性；
- 报价映射；
- 报价有效性；
- 总价；
- 用户预算；
- 最终 Build Snapshot。

验证失败后，允许有限次数重新求解。

建议默认最多一次自动重新求解，必要时使用配置项调整。

### response\_generator

输入必须是已经通过业务验证的 BuildResult。

使用 LLM 生成：

- 推荐总结；
- 选型理由；
- 性能表现解释；
- 预算分配解释；
- 兼容性注意事项。

商品价格、购买链接、型号、SKU 和总价必须从结构化数据中渲染。

不允许由 LLM 重新创造这些字段。

如果模型不可用，应提供确定性的基础配置展示，而不是丢失已经完成的求解结果。

## 7.4 PCConfigState

设计独立、强类型的工作流状态。

推荐字段：

- user\_message
- requirements
- validation\_result
- candidate\_pool\_id
- build\_id
- compatibility\_report
- budget\_report
- retry\_count
- workflow\_status
- clarification\_required
- final\_result

根据现有 AgentState 结构和 LangGraph API 适配。

不得重复保存庞大的商品和硬件列表。

不得在 State 中保存模型密钥、服务密钥、完整 JWT 或其他敏感凭证。

Checkpointer 仍使用现有机制。

不得为 PC 工作流建立第二套用户会话身份体系。

## 7.5 PC Tools

本次工具：

- search\_hardware\_candidates
- get\_benchmark\_data
- get\_verified\_offers
- solve\_pc\_build
- validate\_pc\_build

所有工具必须使用现有 ToolSpec 治理体系。

包括：

- timeout；
- retry；
- permission；
- output sanitization；
- output token limit；
- per-turn quota；
- error isolation；
- metrics。

模型不得直接调用原始 API 或数据库。

外部数据获取不通过 Agent 临时任意 HTTP 请求实现。

## 7.6 失败处理

工具错误应区分：

- 无候选；
- 报价不存在；
- 报价过期；
- 预算无解；
- 不兼容；
- 未知参数；
- Java 控制面不可用；
- 超时；
- 模型调用失败。

不能把所有错误都转换成一段普通文字，让 LLM 自行解释并掩盖系统故障。

应使用明确的结构化错误和安全用户提示。

***

# 8. Prompt 设计规范

不得将所有业务逻辑放入一个巨大 System Prompt。

至少分为：

- `pc_config_system.md`
- `requirement_parser.md`
- `response_generator.md`

未来预留：

- `hardware_reviewer.md`
- `comparison_analyzer.md`
- `bottleneck_analyzer.md`
- `replacement_planner.md`

## 8.1 System Prompt 必须包含的规则

1. 你是面向中国大陆消费者的 PC 配置顾问。
2. 硬件、报价、性能必须来自业务工具。
3. 不得编造硬件参数。
4. 不得编造 PassMark 分数。
5. 不得编造商品链接。
6. 不得编造价格和库存。
7. 不得绕过配置求解器。
8. 不得绕过预算校验。
9. 不得绕过兼容性校验。
10. 用户明确指定的硬约束不得擅自修改。
11. 软偏好可以权衡，但必须解释。
12. 找不到商品时必须明确说明。
13. 报价过期时不能当作有效报价。
14. 推荐理由必须能够得到数据和技术资料支持。
15. 区分事实、性能估算和主观评价。
16. 缺少关键数据时明确说明。

不要要求模型暴露隐藏的内部推理过程。

只要求它输出简洁、可核验的推荐依据。

## 8.2 Prompt 与 Workflow 解耦

Prompt 文件不能包含数据库查询逻辑、硬件兼容性计算、价格计算和业务权限。

这些都由代码完成。

未来调整 Prompt 不应该要求修改 Java Solver。

***

# 9. SSE 和前端集成

延续现有 SSE 契约：

- citations
- reasoning
- token
- tool\_call
- tool\_result
- done
- error

不得随意增加事件类型。

如果本次仅使用已有 token 事件输出 Markdown，就不需要修改 SSE Schema。

如果现有 OpenUI 能力已经能够满足结果展示，可以复用。

但 OpenUI 不应该成为三天 Demo 的前置条件。

前端最终必须展示：

1. 需求总结；
2. 八件硬件；
3. 硬件主要参数；
4. 单件价格；
5. 商品购买链接；
6. PassMark 数据；
7. 总价；
8. 预算状态；
9. 兼容性状态；
10. 报价核验时间；
11. 推荐说明。

最终配置必须从结构化结果生成。

不得让 LLM 自行重新组织商品链接后再输出。

***

# 10. 持久化和未来扩展接口

本次只实现必要的基础能力。

但需要建立长期稳定的业务对象：

## PC Build

配置方案必须有唯一 build\_id。

应保存不可变的配置快照。

至少记录：

- requirements\_snapshot
- components\_snapshot
- offer\_snapshot
- benchmark\_snapshot
- compatibility\_report
- budget\_report
- total\_price\_fen
- solver\_version
- rule\_version
- created\_at

未来功能统一围绕 PC Build 实现：

### 智能配置对比

读取两个或多个 Build Snapshot，比较：

- 性能；
- 价格；
- 适用场景；
- 升级空间；
- 组件差异。

不重新实现商品数据库或配置求解器。

### 智能瓶颈分析

读取 Build、Benchmark 和 Workload Profile。

不重新实现硬件检索。

### 交互式硬件替换

读取原 Build，锁定用户指定的组件，替换目标组件，重新调用 Solver 和 Validator。

新方案产生新的 Build，不直接覆盖历史快照。

## 扩展接口

优先保持以下业务边界：

- HardwareCatalogRepository
- BenchmarkRepository
- OfferRepository
- BuildRepository
- BuildSolver
- CompatibilityValidator

不要为了遵循接口清单而过度抽象。

只有真正需要替换实现的地方才定义 Port / Adapter。

***

# 11. 未来能力的接入位置

本次不实现以下功能，但必须在架构文档说明其接入方式。

## RAG

用途：

- 厂商官方说明书；
- 硬件技术知识；
- BIOS 和接口兼容说明；
- 硬件性能限制及风险解释。

接入位置：

`knowledge_retriever` 节点。

不得使用向量数据库替代结构化硬件和商品查询。

## MCP

作为未来外部标准工具接入协议。

不取代当前 Java Internal API。

内部硬件目录、预算求解和兼容性检查继续使用业务 API / ToolSpec。

## HITL

未来适用于：

- 需求确认；
- 商品匹配审批；
- 配置方案确认；
- 硬件替换确认。

采用 LangGraph interrupt / resume。

在需要人工决策的节点中断。

不得让每次普通工具调用都要求人工审批。

## Multi-Agent

未来最多先考虑：

- Requirement Analyst
- Recommendation Planner
- Hardware Reviewer

不要建立八个分别负责 CPU、GPU、主板等硬件的 Agent。

Compatibility Engine 和 Solver 永远保持确定性业务组件，而不是 Agent。

***

# 12. 三天工作量与优先级控制

按照以下优先级推进，而不是严格按照日期安排。

## P0：必须完成

- 真实仓库检查；
- Demo 硬件候选数据；
- 八类别完整数据；
- PassMark 关联；
- 人工核验商品及报价；
- Java 数据查询；
- 确定性配置求解；
- 基础兼容性验证；
- 严格预算校验；
- 独立 PC Config Graph；
- Prompt；
- 前端结果展示；
- 端到端联调；
- 原有功能回归。

## P1：尽量完成

- Build Snapshot 持久化；
- 版本化数据模型；
- 完整业务文档；
- Fake LLM 评测；
- 结构化错误；
- Workflow Feature Flag。

## P2：不在本次实现

- 全量数据清洗；
- 商品自动匹配后台；
- 电商 API 自动采集；
- OR-Tools；
- 多 Agent；
- RAG；
- MCP；
- 高级 HITL；
- 多套配置对比；
- 瓶颈分析；
- 硬件交互替换。

如果时间不足，优先缩小 Demo 数据集，不得降低预算、商品真实性和关键兼容性检查要求。

***

# 13. 项目扩展治理：防止未来推倒重来

这是强制要求。

每次新增业务功能必须遵循：

1. 新增独立业务模块或 Feature。
2. 尽量复用现有核心能力。
3. 保持原接口向后兼容。
4. 使用明确的结构化数据契约。
5. 不改写无关模块。
6. 不将业务数据塞进全局 AgentState。
7. 不让新业务反向依赖原有通用基础模块中的具体实现。
8. 不允许新功能强制依赖尚未启用的未来能力。

建立独立的 PC 配置架构文档体系：

`docs/pc-config/`

至少包含：

- README.md
- demo-scope.md
- architecture.md
- agent-workflow\.md
- agent-state-and-tools.md
- data-model.md
- data-quality-and-lifecycle.md
- market-offer-management.md
- solver-and-compatibility.md
- api-contract.md
- testing-and-evaluation.md
- extension-roadmap.md
- decisions/ADR-001-agent-workflow\.md
- decisions/ADR-002-data-source.md
- decisions/ADR-003-build-solver.md
- decisions/ADR-004-build-snapshot.md

文档必须反映真实代码。

不允许先创建大量空洞文档，再声称架构设计已经完成。

对每项重要设计决策说明：

- 背景；
- 选择；
- 取舍；
- 不选择其他方案的原因；
- 未来替换路径；
- 对旧工程的影响。

每完成一个重要功能，更新对应文档。

以后其他 Coding Agent 应当只需要阅读项目现有权威文档和 PC 配置文档，就能理解当前系统，不需要依赖本次开发对话的聊天历史。

***

# 14. 测试与评测要求

必须保留现有质量基线。

新增：

## Java

- Hardware Repository 测试；
- Benchmark 映射测试；
- Offer 状态测试；
- Solver 单元测试；
- 预算边界测试；
- Compatibility Rule 测试；
- API 集成测试；
- Build Snapshot 测试。

## Agent

- Requirement Parser Schema 测试；
- 需求硬约束 / 软偏好区分测试；
- Workflow 路由测试；
- 节点输入输出测试；
- ToolSpec 权限和超时测试；
- 无候选测试；
- 预算无解测试；
- 重试上限测试；
- Fake LLM Graph 测试；
- 最终输出与 Java BuildResult 一致性测试。

## Frontend

- 八硬件结果渲染；
- 商品链接正确性；
- 总价展示；
- 预算状态；
- 兼容性状态；
- 无解状态；
- 原有聊天回归。

## 必须满足的业务指标

- 最终成功配置必须恰好包含八种硬件类别。
- 严格预算超支次数必须为 0。
- 已知硬性兼容冲突进入成功方案的次数必须为 0。
- 虚构商品链接次数必须为 0。
- 虚构价格次数必须为 0。
- 无法验证的关键规格不得展示为已兼容。
- 工具错误不得伪装为正常推荐。

至少建立一套固定 Demo 测试输入和预期业务结果。

***

# 15. 执行模式与最终交付

不要将本任务变成只输出计划的分析任务。

完成必要检查后，直接进入实施。

采用连续小步交付：

- 检查；
- 实施；
- 测试；
- 更新文档；
- 继续下一项。

允许并行开发数据脚本、独立 DTO 或互不依赖的测试，但必须避免多人或多个 Agent 同时修改同一核心文件造成冲突。

不允许在尚未验证核心接口时先大规模开发前端。

不允许先编写全部未来功能再回来验证 Demo。

不允许因为测试失败而降低断言或删除测试。

对不确定的实现细节，先检查实际代码，再选择最小且符合现有架构的实现方案。

## 最终必须交付

1. 可以运行的 PC 配置 Agent。
2. Demo 硬件候选数据集。
3. PassMark 映射数据。
4. 人工核验商品和价格数据。
5. Java PC 配置业务接口。
6. 确定性配置求解器。
7. 基础兼容性与预算校验。
8. 独立 LangGraph PC Configuration Workflow。
9. 前端配置结果展示。
10. PC 配置架构与扩展文档。
11. 新增测试和评测。
12. 完整的旧功能回归结果。
13. 当前未完成事项及后续升级路线。

最终报告必须明确：

- 新增和修改了哪些文件；
- 实际实现了哪些功能；
- Agent Graph 的真实结构；
- 节点及工具之间的调用关系；
- Java 和 Agent 接口；
- 数据来源及商品审核情况；
- 预算与兼容性验证方式；
- 哪些功能只是预留而没有实现；
- 哪些地方与本文原始方案存在差异；
- 测试执行结果；
- 下一阶段应该从哪些具体文件和模块继续开发。

**最终目标：得到一个可实际演示的 PC 配置推荐产品，以及一套能够支持后续持续升级、不依赖本次开发对话历史的工程架构和文档。**
