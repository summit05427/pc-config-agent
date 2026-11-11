# Stage 9：核心硬件优先的第三方商品映射与可信报价接入——完整规划任务

## 0. 决策修订（v2，2026-11-09）

| 编号 | 决策 | 对本方案的影响 |
| --- | --- | --- |
| Q1 | 项目定位为本地化、封闭式、非商业学术研究；`chengkit-taobao` 不标记 BLOCKED，不做代码隔离，抓取数据可直接入库，风险由负责人书面承诺兜底 | 删除「商业许可阻塞」表述；改为在文档中声明非商业用途、数据来源与追溯要求 |
| Q2 | 报价继续使用 `classpath:pc-config/offers.json` + `JsonOfferRepository`；不建 Offer / Mapping / Import Batch 表，不新增 Flyway 迁移 | Stage 9.4 由「数据库导入」改为「整份 JSON 校验后发布 + `Offer` record 兼容扩展」 |
| Q3 | 首期平台为淘宝，作为当前首选数据源 | 删除「只有京东侧才适用」的矛盾表述；京东列为后续备选供应商 |
| Q4 | P0 = standard-build 池 ∧ `recommendation_status=ELIGIBLE` ∧ `category_specific_readiness=READY`；不使用 `market_status` | Stage 9.1 新增派生就绪度判定；`mapping_priority` 只存在于离线产物 |
| Q5 | 首批 8 款（每类 1 款）组成一套完整兼容配置；通过后扩到 16 款 | Stage 9.5 的验收门槛由「每类 2 款」下调为「首批 8 款」 |

### 0.1 事实基线更正（以当前代码为准）

- 当前**不存在 Offer 数据库表**。报价唯一来源是 `application-service/src/main/resources/pc-config/offers.json`，由 `JsonOfferRepository` 读取；现有 28 条，其中 10 条 `OWNER_VERIFIED`、18 条 `MOCK_DEMO`。
- Flyway 最新版本为 `V24`，只有 `pc_build_snapshots`；报价以 `offer_snapshot jsonb` 完整写入快照，无需改表。
- `Offer.isUsableOn()` 同时接受 `VERIFIED` 与 `MOCK`；`cheapestUsableByHardware(asOf, requireVerified=false)` 会选到演示价。
- Agent `candidate_retriever` 以 `verified_only=False` 拉取报价；`build_solver` 重试时强制 `require_verified_offers=false`。
- `Offer` 是 16 字段 record，没有 `mapping_id`、`provider`、`provider_batch_id`、`price_basis`、`availability_status`。

### 0.2 第二轮决策（Q6–Q10）

| 编号 | 决策 | 对本方案的影响 |
| --- | --- | --- |
| Q6 | P0 谓词去掉「standard-build 池」条件，改为 `recommendation_status=ELIGIBLE ∧ category_specific_readiness=READY` | 机箱/散热器/电源的 `lifecycle_status` 全为 `UNKNOWN`，按池筛选会让三类 P0 为 0，与八类覆盖目标冲突 |
| Q7 | `price_source` 新增 `PLATFORM_OBSERVED`，规则核验通过后才升为 `OWNER_VERIFIED`（Q16 修订）；生产求解只接受 `OWNER_VERIFIED` | 同步 `Offer`、`OfferResponse`、`offers.json`、Agent schema 与前端展示 |
| Q8 | `Offer` 只加 `price_basis`、`observed_at`、`provider`、`availability_status`（Q16 追加 `verification_method`）五个可空字段；`final_payable` 本期不加 | `platform` 表示电商平台，`provider` 表示采集工具或数据来源，二者不重复 |
| Q9 | `valid_until` 缺失时按 14 天 TTL 补齐；首期为一次性验证，不做周期刷新 | 刷新做成 `scripts/pc-config/` 的手动入口，不排期 |
| Q10 | 旧 10 条 `OWNER_VERIFIED` 报价只复核与首批 8 款相关的条目，其余丢弃 | 整份重写前先做差集核对，避免误删仍有效的报价 |

### 0.3 第三轮决策（Q11–Q15）

| 编号 | 决策 | 对本方案的影响 |
| --- | --- | --- |
| Q11 | 首批参考配置取主流档，预算区间 7,000–9,000 元 | 8 款按主流档选型，保证在售与规格完整 |
| Q12 | 新增字段使用受控枚举与固定时间格式 | 见 §5.4 枚举表；发布脚本强校验，禁止自由字符串 |
| Q13 | POC 去掉人工逐条核对，改为规则自动校验 | §6.4 的 POC 顺序调整；核验语义需同步修订 ADR 0011 |
| Q14 | 报价沿用硬件 `catalog_version`，同版本内可多次发布，用 `observed_at` 与批次区分 | 不引入第二套版本号 |
| Q15 | 新增 ADR 0018、0019、0020 | 记录文件形态、来源分离、非商业定位三项决策 |

### 0.4 第四轮决策（Q16–Q17）

| 编号 | 决策 | 对本方案的影响 |
| --- | --- | --- |
| Q16 | 取消人工逐条核对，改为确定性规则自动核验；新增 `verification_method=RULE\|MANUAL`；新增 ADR 0021 取代 ADR 0011 | 核验从「人」变为「可测试的规则」；规则不通过一律记 `PLATFORM_OBSERVED`，不得升级 |
| Q17 | 发布采用「同目录临时文件 → 全量校验 → `os.replace` 原子替换」，回滚靠 Git | 写入中断不会留下半份 JSON；不额外保留报价副本 |

## 一、你的角色与任务目标

你是一名负责大型 Agent 应用架构演进的资深全栈架构师，同时具备以下能力：

- Java 21 / Spring Boot / Spring Modulith 后端架构设计；
- Python / LangGraph Agent 服务架构；
- React / TypeScript 前端架构；
- PostgreSQL、数据治理、ETL 和数据导入设计；
- 商品数据建模、硬件规格匹配、市场报价治理；
- 自动化测试、集成测试和生产环境质量治理。

当前项目是一个基于 LLM 的 PC 配置智能推荐 Agent 应用。项目并不是从零开发，而是在已经完成基础架构和 Stage 1–6 的四端应用模板上进行垂直业务开发。

本次任务是全面分析并规划 **Stage 9：第三方商品映射与可信报价接入**。

本阶段的核心目标不是采集尽可能多的电商商品，而是：

**优先取得当前真正有购买价值的主流硬件商品和可靠报价，使系统能够基于真实中国市场数据，生成预算准确、硬件兼容、具备真实购买链接的完整 PC 配置。**

必须坚持以下原则：

1. 核心硬件优先，已停产、过时、冷门硬件延后处理。
2. 数据身份准确优先于商品数量。
3. 报价可信优先于价格覆盖率。
4. 低频、人工主导的采集优先于高频自动化采集。
5. Java Application Service 继续作为商品映射、报价、预算、求解和快照的权威。
6. 不新增没有必要的微服务，不重构已经完成的 Agent 工作流。
7. 不允许为了提高采集效率而尝试绕过淘宝的风控或反爬机制。
8. 所有实施内容必须建立在当前真实代码、真实数据和实际第三方能力之上，禁止根据旧计划臆造代码结构或接口。

**本轮只进行仓库审计、第三方准入评估和完整实施计划编制，不修改业务代码、不执行真实商品采集、不进行数据库迁移。**

最终需要形成一份可以拆分为多个独立实施任务的 Stage 9 实施方案。

---

## 二、项目背景与必须继承的架构事实

### 2.1 当前四端架构

项目采用 Monorepo 结构：

服务

技术栈

核心职责

frontend

React 19 + TypeScript + Vite

用户 PC 配置界面、SSE 消费、配置卡片展示

admin

React 19 + TypeScript + shadcn-admin

独立管理端

application-service

Java 21 + Spring Boot + Spring Modulith

用户身份、业务数据、硬件数据、报价、求解、预算、快照

agent-service

Python 3.12 + FastAPI + LangGraph + LangChain

需求解析、Agent 工作流编排、解释和结构化响应

基础设施包括：

- PostgreSQL；
- Redis；
- LiteLLM；
- Nginx；
- Java 与 Agent 分离的数据存储。

架构权威边界：

- Java 是硬件目录、Benchmark、Marketplace Offer、兼容性、预算、求解和 Build Snapshot 的唯一业务权威。
- Agent 只通过 Java 内部 API 获取业务数据。
- Agent 不直接访问 Java 数据库。
- 前端不直接访问第三方电商服务。
- 不允许第三方商品服务直接成为 Agent 的运行时依赖。

当前 Agent 已使用确定性 PC 配置 Graph，不再是通用 ReAct 工作流。

现有工作流：

`START → requirement_parser → requirement_validator → candidate_retriever → build_solver → build_validator → response_generator → END`

现有 Agent 工具包括：

- `search_hardware_candidates`
- `get_benchmark_data`
- `get_verified_offers`
- `solve_pc_build`
- `validate_pc_build`

Stage 9 原则上只涉及商品数据获取、校验、导入和 Java 报价数据源，不应重做上述工作流。

### 2.2 Stage 1–6 已交付的历史基线

此前实施报告记录：

- Stage 1–6 已完成；
- 已建立 Java `pcbuild` 模块；
- 已存在 `HardwareCatalogRepository`、`BenchmarkRepository`、`OfferRepository`、`BuildSnapshotRepository`；
- 已存在 `OfferQueryService`；
- 已实现内部硬件、Benchmark、Offer、Build 求解和快照查询接口；
- 已存在 V24 Build Snapshot 数据库迁移；
- Agent 已经通过 Java 内部接口获取可信 Offer；
- 前端已经支持 `done.build_result` 和配置卡片；
- Stage 5 已完成三端核心流程 E2E；
- Stage 6 已建立 `docs/pc-config/` 文档体系。

历史报告中的报价数据为：

- 10 条人工核验的 VERIFIED 报价；
- 18 条 MOCK 报价，带有 `price_source=MOCK_DEMO` 和 `data_status=MIXED_DEMO`。

以上只是历史基线，不代表当前仓库仍然保持这些数量与状态。

**必须重新读取当前代码和真实数据。严禁直接将历史报告里的数字、Git 分支、HEAD、Flyway 版本和工作区状态视为当前事实。**

### 2.3 Stage 8 已确认的设计决策

Stage 9 必须继承 Stage 8 的决策，不得擅自重新设计。

编号

决策

Stage 9 必须遵循的要求

Q1

数据资产采用版本化 JSONL，Parquet 可作为派生格式

Stage 9 从 Stage 8 发布的数据资产读取候选硬件

Q2

Stage 8 不修改 Java 运行时

Stage 9 才负责将真实商品映射与报价接入现有 Java 运行时

Q3

旧 `data_quality_status` 保留

不破坏 `VERIFIED_STRUCTURED / PARTIAL` 的既有语义

Q4

Lifecycle 与推荐资格分离

`lifecycle_status=UNKNOWN` 不自动代表不可推荐

Q5

继续演进 `scripts/pc-config/`

不新建重复 ETL 流程

Q6

工作区修改必须保护

不擅自清理、覆盖、重置或提交用户已有修改

Stage 8 的目标数据资产预计包括：

- `hardware-master.jsonl`
- `benchmark-master.jsonl`
- `candidate-pools/`
- `catalog` 与数据批次 Manifest
- 数据质量报告
- 第三方商品映射输入清单

实际路径、文件名、字段和版本必须以当前仓库的真实交付为准，不得假定所有文件已经创建。

---

## 三、第三方工具：chengkit-taobao 的实际情况

本项目负责人选择评估的第三方工具：

GitHub：

<https://github.com/banxia79009/chengkit-taobao>

项目负责人已经提供了 `chengkit-taobao` 的本地实测报告，测试日期为 2026-11-09。

实测报告记录的关键事实如下：

项目

已知情况

项目版本

v1.1.0

运行方式

MCP + OpenCLI + 本机真实 Chrome

操作系统

Windows

浏览器

用户已经登录的 Chrome

工具数量

14 个 MCP 工具

搜索能力

`taobao_search` 已在真实淘宝页面实测通过

商品详情

`taobao_read_item` 尚未完成实测

SKU 信息

`taobao_read_sku` 尚未完成实测

商品详情、SKU、价格联动

不能视为已经验证

无头服务器运行

不属于当前项目已验证能力

自动并发采集

不提供

运行方式

依赖真实本地浏览器会话，不是可以直接部署在 Java 云服务器上的 HTTP API

实测报告中记录的节流和停止机制：

- 普通任务冷却约 90 秒；
- 页面内部动作间隔约 10 秒；
- 检测到登录或验证码时进入约 30 分钟冷却；
- 遇阻后停止，等待人工处理；
- 不通过自动刷新掩盖失败；
- 不提供批量并发采集。

项目未实现反爬对抗手段，不承诺绕过淘宝风控。

### 3.1 使用定位与数据追溯

当前公开仓库 LICENSE 为 `PolyForm Noncommercial License 1.0.0`（<https://github.com/banxia79009/chengkit-taobao/blob/main/LICENSE>）。

项目负责人已确定本项目的使用定位：**本地化、封闭式、非商业性质的学术研究**，不产生商业收益，不对外交付商业服务。

据此：

- `chengkit-taobao` **不标记为 BLOCKED**，不做代码隔离。
- 允许将其抓取或解析的商品数据直接导入本仓库的报价产物。
- 风险由项目负责人的书面承诺兜底，记录在 `docs/pc-config/market-offer-management.md` 的数据来源章节。
- 定位一旦变化（对外交付、商业收益、公开发布数据），必须暂停该数据链路并重新评估许可证约束。

仍然保留的约束：

- 每条报价必须可追溯来源：`price_source`、`provider`、`price_basis`、`observed_at` 均不得为空或伪造。
- 不得把平台返回的匹配分数、标题相似度或搜索排名当作 `VERIFIED`。

### 3.2 不能假定所有工具都已经可用

特别注意：

实测报告只证明 `taobao_search` 能够返回真实商品搜索结果。

以下能力还必须先通过小范围实机验收：

- `taobao_read_item`
- `taobao_read_sku`
- 商品详情中的标准型号提取；
- SKU 规格与价格对应关系；
- SKU 当前状态；
- 商品链接的可用性。

不能将 README 或工具描述中的能力直接当成实测结果。

在 Stage 9 计划中，将这些能力列为 POC 验证项。

---

## 四、Stage 9 的业务目标：核心硬件优先

本项目已有数千条硬件原始数据，但不能把所有硬件都立即转换为电商商品搜索任务。

主要原因：

1. 商品搜索和详情读取依赖真实浏览器操作；
2. 当前工具没有可靠的批量并发能力；
3. 淘宝可能触发验证码、登录限制或访问风控；
4. 过时硬件的商品检索价值较低；
5. 模糊商品结果很容易出现错误型号和规格变体；
6. 当前最重要的是建立能实际生成完整配置的核心商品库。

因此，Stage 9 不再以“全量硬件映射”为目标，而是先建立分级商品映射范围。

### 4.1 P0：核心主流硬件

第一阶段必须优先处理。P0 使用 Stage 8 已发布字段的确定性组合判定，不引入新的主数据字段：

```
P0 = recommendation_status = ELIGIBLE
   ∧ category_specific_readiness = READY
```

**不把 `standard-build` 池作为 P0 条件**：该池按 `lifecycle_status ∈ {CURRENT, MATURE}` 筛选，而机箱、散热器、电源的 `lifecycle_status` 当前 100% 为 `UNKNOWN`（Stage 8 允许），三者池内记录为 0。用池筛选会让这三类无法进入 P0，与「八类各 1 款」目标冲突。

实测 P0 数量（2026-11-09 批次）：

| 类别 | ELIGIBLE ∧ READY |
| --- | --- |
| CPU | 130 |
| GPU | 491 |
| 主板 | 684 |
| 内存 | 1,467 |
| 存储 | 1,272 |
| 散热器 | 863 |
| 机箱 | 1,071 |
| 电源 | 518 |

`category_specific_readiness` 是 Stage 9.1 的派生判定，只写入映射任务清单，不写回主数据：

| 类别 | READY 条件 |
| --- | --- |
| CPU / GPU | `hardware-benchmarks.jsonl` 中该 `hardware_id` 存在 `MATCHED` 记录，且关键规格完整 |
| MOTHERBOARD | `socket`、`chipset`、`memory_type` 非空 |
| MEMORY | `memory_type`、`capacity_gb` 非空 |
| STORAGE | `capacity_gb`、`interface`、`form_factor` 非空 |
| COOLER | `supported_sockets`、`cooler_type` 非空 |
| CASE | `supported_mainboard_form_factors`、`max_gpu_length_mm` 非空 |
| PSU | `wattage_w`、`pcie_8pin_count` 非空 |

- 不使用 `market_status` 作为筛选条件：该字段当前 8,238 条全部为 `UNVERIFIED`，不具备判别力。
- `mapping_priority` 只写入 `marketplace-mapping-requests.jsonl`，不进入 Java Domain，不修改 Stage 8 字段语义。
- 检索键复用 Stage 8 已生成的 `search_queries`；缺失记录单独输出待补齐清单。

### 4.1.1 `sellable` 判定层（Q19 新增，必须实现）

P0 谓词只回答「数据能不能用」，不回答「今天还能不能买到」。Q19 要求采集目标是清洗后的可售集合，因此 Stage 9.1 必须额外产出一个 `sellable` 子集。

现状约束（以当前数据为准）：

- `lifecycle_status` 在机箱、散热器、电源三类为 100% `UNKNOWN`，单独用它筛会把三类清零；
- `market_status` 全量为 `UNVERIFIED`，无判别力；
- 主数据是全球抓取，含大量国内无渠道品牌（Aerocool、Alpenföhn、Akasa 等），这些条目即使有报价也没有购买价值。

因此 `sellable` 由三条独立信号共同判定，缺一不可，且都能从现有数据派生：

| 信号 | 判定 | 说明 |
| --- | --- | --- |
| 品牌可售性 | `brand` 在「中国区在售品牌白名单」内 | 白名单由人工维护，首期覆盖 DIY 主流品牌；名单外一律不进 `sellable` |
| 型号年代 | 从 `model_name` 解析代号或芯片型号，落在当前主流代际区间内 | CPU/GPU 用芯片代号；主板用 `chipset`；内存 `DDR4/DDR5` + 速率；存储 `PCIe 3.0/4.0/5.0` |
| 市场存在性 | 族搜索能命中至少 1 条非二手 listing | 搜索命中即视为「在售」；命中不了说明该型号国内无货或已退市 |

判定结果只写入映射任务清单，不写回主数据，不改变 Stage 8 字段语义。原先按 `lifecycle_status ∈ {CURRENT, MATURE}` 筛选 `standard-build` 池的做法继续不用于本阶段（Q6 结论不变）。

`mapping_status` 取值：`PENDING` / `LISTING_FOUND` / `OBSERVED` / `NO_LISTING` / `EXCLUDED_NOT_SELLABLE`。`NO_LISTING` 不是失败，而是「搜索确认国内无货」的有效结论。

P0 必须覆盖八个硬件类别：

1. CPU
2. GPU
3. 主板
4. 内存
5. SSD / 存储
6. 散热器
7. 机箱
8. 电源

建议优先顺序：

1. CPU
2. GPU
3. 主板
4. 内存
5. SSD
6. 电源
7. 散热器
8. 机箱

这个顺序是数据采集规划顺序，不代表其他硬件可以不采集。首期必须有能力构成完整八件套配置。

### 4.2 P1：仍有购买价值的上一代产品

暂缓批量映射，但保留后续入口。

包括：

- 价格具有竞争力的上一代 CPU；
- 仍在正常零售的上一代 GPU；
- 仍有库存且性价比合理的主板；
- 仍然有购买需求的 DDR4 等硬件；
- 价格合理、具有实际用途的其他上一代配件。

不能仅凭发布时间决定是否属于 P1。

需要综合产品生命周期、市场可获得性、价格优势和实际推荐价值。

### 4.3 P2：停产、过时和冷门硬件

初期暂不进行批量商品映射。

包括：

- 已停产且市场库存稀少的型号；
- 已被多代产品替代且缺少推荐价值的型号；
- 极少数商家销售的型号；
- 商品身份和关键规格难以确认的产品；
- 只对特殊老电脑升级有价值的旧硬件。

P2 只能被标记为暂缓映射，不得直接删除 Stage 8 的硬件主数据。

### 4.4 优先级与硬件自身状态分离

Stage 9 的映射优先级不能覆盖 Stage 8 的硬件质量、生命周期和推荐资格。

必须分别理解：

字段

语义

`data_quality_status`

硬件结构化数据的完整度

`governance_status`

Stage 8 的治理结果

`lifecycle_status`

硬件自身生命周期

`recommendation_status`

是否具备参与推荐的资格

`mapping_priority`

Stage 9 商品映射的先后顺序

`mapping_status`

当前商品映射处理进度

实际是否需要新增字段必须先审计现有模型。

严禁：

- 因为是 P2，就直接改为 `OBSOLETE`；
- 因为没有商品映射，就将硬件改为 `EXCLUDED`；
- 因为 `lifecycle_status=UNKNOWN`，就自动排除所有硬件；
- 修改 Stage 8 已经确认的字段语义。

如果当前模型没有 `mapping_priority` 或 `mapping_status`，应评估将其放在离线映射任务 Manifest 中还是 Java 商品映射记录中，优先选择低复杂度设计。

---

## 五、核心架构设计目标

Stage 9 最终形成以下数据链路：

```
Stage 8 版本化硬件候选池
          │
          ▼
P0 / P1 / P2 优先级筛选
          │
          ▼
Marketplace Mapping Request
          │
          ▼
经授权的第三方商品获取工具
或合规的人工商品数据来源
          │
          ▼
结构化商品映射和报价导出
          │
          ▼
标准化 / 身份校验 / 报价校验
          │
          ▼
异常隔离 + 导入预览
          │
          ▼
Java Application Service
          │
          ▼
PostgreSQL 商品映射和可信 Offer
          │
          ▼
OfferRepository
          │
          ▼
BuildSolver
          │
          ▼
Build Snapshot
```

### 5.1 必须区分三个业务实体

商品身份、平台商品映射和报价不能混成一个字段或一条数据。

至少需要在设计中区分：

**A. Hardware**

Stage 8 的标准硬件：

- `hardware_id`
- `category`
- `brand`
- `model_name`
- `specifications`
- 生命周期及推荐资格
- catalog version

**B. Marketplace Product Mapping**

标准硬件与平台具体商品之间的关系：

- `mapping_id`
- `hardware_id`
- `provider`
- `platform`
- `platform_product_id`
- `platform_sku`（如果对应具体变体）
- `title`
- `product_url`
- 商品身份核验状态
- 核验依据
- 来源批次

**C. Marketplace Offer**

某个商家在某一时刻对商品提供的报价：

- `offer_id`
- `mapping_id`
- `hardware_id`
- `seller_id`
- `seller_name`
- `seller_type`
- `price_fen`
- `currency`
- `price_type`
- `price_basis`
- `observed_at`
- `valid_until`
- `availability_status`
- `verification_status`
- `provider`
- `provider_batch_id`
- `purchase_url`

以上是**逻辑边界**，不是三张数据库表。按 Q2，本期不新建 Offer / Mapping / Import Batch 表：商品映射是离线产物（映射请求清单与采集结果），报价仍落在 `pc-config/offers.json`，`Offer` record 只做向后兼容的可空字段扩展。

必须先读取现有 `Marketplace Offer` 和 `OfferRepository` 的实际实现，判断是否需要拆分实体以及怎样兼容旧数据。

商品身份与报价要分离：

- 一个标准硬件可以映射多个平台商品；
- 一个平台商品可能有多个商家报价；
- 同一个商品价格会随时间变化；
- 不同商家出售同一个 SKU 时应当保留为不同 Offer；
- Build Snapshot 保存的是配置生成时选中的商品和报价。

### 5.2 价格口径必须独立

必须区分：

- 搜索结果展示价；
- 商品详情展示价；
- SKU 面板价；
- 公开促销价；
- 会员专享价；
- 优惠券价；
- 购物车价；
- 最终支付金额。

建议设计两个不同的概念：

- `price_type`：价格属于普通公开价、促销价、会员价还是优惠券价；
- `price_basis`：价格来自搜索列表、商品详情、SKU 面板还是其他页面。

例如：

```
{
  "price_fen": 429900,
  "currency": "CNY",
  "price_type": "PUBLIC_PROMOTION",
  "price_basis": "SKU_PANEL",
  "final_payable": null,
  "observed_at": "2026-11-09T10:00:00+08:00"
}
```

这是内部数据结构示意，不是第三方实际返回契约。

必须遵循：

- 金额全部采用整数分；
- 禁止使用 float/double 进行金额计算；
- 不得将展示价误认为最终支付价；
- 未确认优惠适用条件时不得推算最终价格；
- 优先采用普通公开价或适用于所有用户的公开促销价；
- 会员专享和个性化优惠首期不参与默认预算求解；
- 未提供 `valid_until` 时，必须设计明确、可配置且可追踪的报价有效期策略；
- 不得伪造报价时间或有效期。

### 5.3 Offer 的状态设计

现有数据契约使用 `match_status=VERIFIED` 作为进入推荐的必要条件。

需要审计当前状态定义，并判断是否应拆分：

- 商品身份状态；
- 报价验证状态；
- 市场可用状态；
- 最终推荐资格。

建议参考：

商品身份：

- `VERIFIED`
- `REVIEW_REQUIRED`
- `REJECTED`

报价验证：

- `VERIFIED`
- `UNVERIFIED`
- `INVALID`
- `EXPIRED`

商品可用性：

- `AVAILABLE`
- `UNAVAILABLE`
- `UNKNOWN`

但不得为了字段数量而过度设计。

可以在内部保持更细粒度状态，同时向现有 `OfferRepository` 提供兼容的最终状态。

最终只有完全通过验证、未过期、符合价格策略的报价才能映射为现有契约所要求的 `match_status=VERIFIED`。

第三方返回的匹配分数、标题相似度或搜索排名不能直接赋予 `VERIFIED`。

**价格来源扩展（Q7）：** 现有 `price_source` 只有 `OWNER_VERIFIED` 与 `MOCK_DEMO`。本期新增 `PLATFORM_OBSERVED`，含义是「页面观测到、尚未人工复核」：

- 生产求解只接受 `OWNER_VERIFIED`；
- `PLATFORM_OBSERVED` 可进入 `offers.json` 与证据展示，但不得参与生产求解；
- 计数口径分离：`verifiedCount` 只统计 `OWNER_VERIFIED`，`mockCount` 只统计 `MOCK_DEMO`，页面观测单独计数。

`final_payable` 本期只作为契约概念存在，不写入 `Offer`（Q8），避免引入恒为 `null` 的字段；确认优惠叠加条件后再作为可空字段加入。

### 5.4 新增字段的受控枚举（Q12）

| 字段 | 取值 | 说明 |
| --- | --- | --- |
| `price_type` | `NORMAL` / `PROMO` / `MEMBER` / `UNKNOWN` | 沿用 `ingest_offers.py` 现有 `PROMO`，不重命名；页面价格标签为空时必须是 `UNKNOWN` |
| `price_basis` | `SEARCH_LIST` / `ITEM_DETAIL` / `SKU_PANEL` | 价格被观测到的页面位置 |
| `availability_status` | `IN_STOCK` / `OUT_OF_STOCK` / `UNKNOWN` | 有价格不等于有货，缺省 `UNKNOWN` |
| `price_source` | `OWNER_VERIFIED` / `PLATFORM_OBSERVED` / `MOCK_DEMO` | 生产求解只接受 `OWNER_VERIFIED` |
| `verification_method` | `RULE` / `MANUAL` | `RULE` 表示由确定性规则核验通过；`MANUAL` 保留给将来人工复核 |
| `observed_at` | ISO-8601 UTC，带 `Z` | 例：`2026-11-09T06:00:00Z` |

枚举值写入 `data-model.md` 与发布脚本校验；新增取值必须先改文档再改代码。

#### 5.4.1 工具返回值到受控枚举的映射（2026-11-09 POC 实测）

`chengkit-taobao` 返回的 `price_type` 不是本项目的受控枚举，发布脚本必须先做确定性映射，禁止透传：

| 工具返回值 | 出现位置 | 映射为 | 说明 |
| --- | --- | --- | --- |
| `displayed_unspecified` | 搜索卡片、详情页、SKU 面板 | `UNKNOWN` | 页面未给出价格性质标签，不能推断为普通价 |
| `displayed_after_subsidy` | 搜索卡片 | `PROMO` | 已扣补贴的展示价，补贴资格未确认，不得据此定价 |
| `selected_sku_panel` | `skus[].price_type` | 不进 `price_type` | 它描述价格来源位置，对应 `price_basis=SKU_PANEL` |

`price_basis` 由工具结果的 `pricing.source` 与调用层级共同确定：`search_card → SEARCH_LIST`、`detail_page_display → ITEM_DETAIL`、`selected_sku_page_display → SKU_PANEL`。按 Q18，入库只接受 `ITEM_DETAIL`（主口径）与 `SKU_PANEL`（详情页无价时的回退），`SEARCH_LIST` 仅用于定位候选。

### 5.5 规则核验（Q16，取代 ADR 0011 的人工核验）

规则版本写入发布清单，规则本身必须有单元测试。全部规则通过才允许把 `price_source` 升级为 `OWNER_VERIFIED` 并写 `verification_method=RULE`；任一不通过则保持 `PLATFORM_OBSERVED`。

| 编号 | 规则 | 不通过时 |
| --- | --- | --- |
| R1 | 身份一致：商家 MPN 与 `manufacturer_part_number` 完全相同；无 MPN 时，型号 token 必须完整命中标题或详情，且不得仅靠标题相似度 | `REJECTED_SPEC_MISMATCH` |
| R2 | 规格一致：在**工具可稳定返回的维度**上逐项核验——`specs_complete=true`、`dimensions` 与 `skus[].specs` 规格名、`stock.status`；详情页 `attributes` / `detail_text` 为空时不得作为核验依据 | `REJECTED_SPEC_MISMATCH` |
| R3 | 价格口径（Q18 修订）：以**商品详情页展示价**为主口径，`price_basis=ITEM_DETAIL`；详情页无价时才读 SKU 面板（`SKU_PANEL`）；搜索卡片价只用于定位，不入库。金额为正整数分，与页面原文一致；禁止汇率折算、折扣推算、凑单推算 | `REJECTED_PRICE_INVALID` |
| R4 | 字段完整：`seller`、`platform_sku`（含 `sku_id`）、`purchase_url`、`observed_at`、`price_basis` 均非空 | `REJECTED_INCOMPLETE` |
| R5 | 唯一映射：同一 `hardware_id` 只允许 1 条通过核验的报价；出现多条通过时全部保留为 `PLATFORM_OBSERVED` 并记 `REJECTED_AMBIGUOUS` | `REJECTED_AMBIGUOUS` |

**POC 第一步实测（2026-11-09，Intel Core i5-14600KF）对本节的修正**：

- 同一商品三层价格不一致：搜索卡片 ¥1169（`displayed_after_subsidy`）、详情页 ¥1169（`price_label` 丢失，降为 `displayed_unspecified`）、SKU 面板 ¥1799（`price_confirmed=true`）。未选规格的展示价是聚合/最低价，只有 SKU 面板价对应可下单单件。
- `taobao_read_item` 返回的 `attributes`、`detail_text` 为空字符串，`detail_images` 为空数组；结构化规格只存在于 `specifications`，而它的值就是 SKU 选项名。**原 R2「详情页规格逐项比对」不可实现**，降级为上述可获取维度核验——**已获负责人批准（2026-11-09）**。
- 多 SKU 商品（本例 9 个 SKU，从 i5-14400F 到 i9-14900KF）必须由 `sku_id` 唯一定位型号，禁止用商品级标题判定；搜索排名第 1 的「CPU+主板套装」应在 R1 阶段直接拒绝。

**Q18（2026-11-09）：价格以详情页为主，接受聚合价偏差**

负责人决定以「快」为先，详情页展示价即可入库，不强制追加 `read_sku` 调用。代价必须显式记录，不能隐藏：

- 多规格商品的详情页展示价是**列表内最低规格价**。本例 i5-14600KF 商品详情页 ¥1169，而 14600KF 对应 SKU 实际 ¥1799，偏差约 35%。
- 因此该报价只代表「该商品链接的展示价」，`price_basis` 必须写 `ITEM_DETAIL`，`notes` 固定注明「多规格商品详情页展示价，非指定型号成交价」。
- 偏差会直接进入预算合计。首期接受该偏差，只要求标注，不做二次复核；当详情页无法给出价格时，才回退到 `read_sku`。

`final_payable` 不参与核验，恒为 `null`。价格分布异常检查（同类价格分位）本期只做告警，不阻断：首期样本量不足以支撑可信区间，强行设阈值等于猜测。

**Q19（2026-11-09）：采集范围是「清洗后的可售集合」，不是 8,238 条原始数据**

负责人明确：数据清洗与分类的目的就是优先筛出当前热门、有货源、可售的商品，剔除已停产 / 无货源 / 国内不可售的条目。因此：

- Stage 9 的目标**不是**在 8,238 条里尽量提高覆盖率，而是**筛选后的可售集合里每一条都要有中国区报价与链接**。不存在「覆盖率折中」这种说法。
- 由此暴露一个必须补的缺口：现有 P0 谓词（`recommendation_status=ELIGIBLE ∧ category_specific_readiness=READY`）实测仍为 6,496 条，占全量 79%，说明它只解决「数据结构可用」，**没有完成可售性筛选**。按 Q19，必须在 Stage 9.1 增加独立的 `sellable` 判定层（见 §4.1.1），采集预算按 `sellable` 集合分配。
- 采集以「型号族」为单位不等于降级：电商同一链接售卖的本来就是同型号不同品牌 / 容量的变体（如「RTX 4060 Ti 8G」一个链接覆盖多个品牌的同芯片卡）。一个 listing 的价格对该族内所有硬件都是真实市场价，族内匹配是数据本身的粒度，不是覆盖率的妥协。
- 采集效率的瓶颈是工具的本地冷却（每次调用约 30 秒），不是匹配精度。因此先按族搜索把 `sellable` 集合覆盖完，再对族内高价差、跨代差大的条目做单件补采。

**Q20（2026-11-09）：`sellable` 判定口径**

| 信号 | 采用口径 |
| --- | --- |
| 品牌 | 国内主流品牌白名单，按类别分别维护；名单外的全球品牌（EVGA、Patriot、Silicon Power、Rosewill、Apevia、Sliger 等）一律不进 |
| 代际 | 当前两代：CPU 13/14 代与 Zen4/Zen5；GPU RTX 40/50、RX 7000/9000、Arc B；主板 700/800 系与 600/800 系芯片组；内存 DDR4/DDR5；存储 PCIe 4.0/5.0 |
| 散热器 / 机箱 / 电源 | 不做代际筛选（无代际概念），用关键规格替代：支持现代插槽、`max_gpu_length_mm` 非空、`wattage_w ≥ 450` |

按此口径实测（2026-11-09，输入 8,096 条）：**可售 3,967 条，占 49%**。

| 类别 | 可售 / 全量 | 占比 |
| --- | --- | --- |
| CPU | 71 / 407 | 17% |
| GPU | 284 / 1,109 | 26% |
| 主板 | 512 / 768 | 67% |
| 内存 | 1,107 / 1,848 | 60% |
| 存储 | 214 / 1,485 | 14% |
| 散热器 | 589 / 863 | 68% |
| 机箱 | 822 / 1,098 | 75% |
| 电源 | 368 / 518 | 71% |

存储可售占比只有 14%，因为主数据里大量是 SATA 与 PCIe 3.0 老盘；CPU 只有 17%，因为全球数据里 12 代及更早占比高。这两类是长尾主要来源，不属于判定错误。

白名单与代际规则实现为 `sellable.py` 并输出 `data/pc-config/export/marketplace/sellable.json`；该文件是 Stage 9.1 的输入，不写回主数据。

---

## 六、chengkit-taobao 的使用边界与 POC 设计

### 6.1 它不是运行时商品 API

即使按 Q1 的使用定位可以直接使用其数据，也必须充分考虑它当前的本机运行模式。

预期工作方式只能先按下面流程评估：

```
开发者本地 Windows
       │
       ▼
chengkit-taobao MCP
       │
       ▼
真实 Chrome 登录会话
       │
       ▼
人工发起低频商品搜索
       │
       ▼
商品详情读取
       │
       ▼
具体 SKU 读取
       │
       ▼
导出结构化采集结果
       │
       ▼
独立校验与导入
       │
       ▼
Java PostgreSQL
```

不要设计成：

```
Agent Service
     │
     ▼
自动请求淘宝 MCP
     │
     ▼
持续采集数千款商品
```

不允许因为 MCP 工具可以被 AI 调用，就将其设计为产品运行时的 Agent 工具。

### 6.2 反爬和平台风控边界

本项目不进行反爬对抗开发。

禁止：

- 代理池轮换；
- 多账号轮换；
- IP 轮换；
- 浏览器指纹伪装；
- navigator 属性补丁；
- 隐藏自动化行为；
- 验证码自动破解；
- 未授权批量并发；
- 高频重复请求；
- 失败后自动刷新、无限重试；
- 降低现有工具安全冷却时间。

不得为了追求采集速度破坏第三方工具的节流机制。

遇到以下情况必须停止：

- 验证码；
- 登录校验；
- 账号访问异常；
- 页面访问被拒绝；
- 工具明确报告风控；
- 需要用户处理的访问阻断。

保留失败原因，等待人工处理。

不得自动尝试绕过限制或通过其他请求方式继续采集。

### 6.3 POC 必须先验证

制定一个独立的 POC 计划，但本轮不要实际执行。

POC 至少覆盖：

1. 工具本地启动；
2. 浏览器会话连接；
3. `taobao_search`；
4. `taobao_read_item`；
5. `taobao_read_sku`；
6. 搜索结果和商品详情是否对应；
7. SKU 规格与价格是否能准确关联；
8. 商品链接是否指向正确页面；
9. 失败和验证码情况下的停止行为；
10. 数据导出格式是否能够被本项目导入。

POC 必须使用少量真实商品、人工操作、允许的请求频率，不得批量采集。

未验证的能力必须明确标记为 `NOT_VERIFIED`，不能在计划中写成已完成。

### 6.4 POC 执行顺序与失败状态（Q13）

POC 分两步，不做人工逐条核对：

1. **能力验证**：用 1 款主流档 CPU 跑通 `search → read_item → read_sku`，由规则校验产出字段完整性（价格、商家、SKU、链接、标题）。
2. **扩量验证**：能力验证通过后扩到首批 8 款。按 Q18，每款只需 `search → read_item`（详情优先），`read_sku` 仅在详情页无价时使用。

失败状态固定为：

| 状态 | 触发条件 | 后续动作 |
| --- | --- | --- |
| `STOPPED_BY_RISK` | 出现登录、验证码或人机校验 | 立即停止，不重试、不刷新绕过，记录冷却时间 |
| `SKIPPED_NO_LISTING` | 搜索无匹配商品 | 记录并继续下一款 |
| `REJECTED_SPEC_MISMATCH` | 标题规格与硬件主数据不一致 | 不进入 offers，写入拒绝清单 |
| `REJECTED_AMBIGUOUS` | 多个商品无法判定唯一目标 | 不进入 offers，写入待定清单 |
| `OBSERVED` | 采集成功但未通过核验规则 | 以 `PLATFORM_OBSERVED` 记录，不参与生产求解 |
| `VERIFIED` | 通过核验规则 | 允许按核验结果升级来源状态 |

#### 6.4.1 POC 第一步结果（2026-11-09，已执行）

| 项 | 结果 |
| --- | --- |
| 选型 | Intel Core i5-14600KF，检索串「英特尔 酷睿 i5-14600KF」 |
| `taobao_search` | 成功，3 条结果，`fetched_at=2026-11-09T09:12:54Z` |
| `taobao_read_item` | 成功，`fetched_at=2026-11-09T09:15:06Z`；`attributes` / `detail_text` 为空 |
| `taobao_read_sku` | 成功，`fetched_at=2026-11-09T09:16:56Z`；`status=ready`，`price_confirmed=true` |
| 采用价格 | 详情页 ¥1169（`price_basis=ITEM_DETAIL`，`price_type=UNKNOWN`）；SKU 面板另测得 ¥1799，按 Q18 不作为主口径 |
| 采用的 SKU | `sku_id=6149347225731`，`14代i5-14600KF 盒装【五年质保】`，`stock.quantity=59`，仅用于确认链接可定位到该型号 |
| 搜索结果质量 | 排名第 1 为 CPU+主板套装，排名第 3 为无关型号；3 条中只有 1 条可映射，印证 R1/R5 的必要性 |
| 运行约束 | 普通冷却 90 秒，任何调用（含失败）都会重置冷却；守护进程空闲退出后需 `daemon restart` 并轮询 `doctor` 至 `extensionConnected=true` |

结论：三步调用全部可用，字段完整度足以支撑 R1、R3、R4；R2 受详情页空规格限制按 §5.5 降级。可以进入第二步扩量验证。

---

## 七、Stage 9 计划拆分

请将 Stage 9 拆分为以下六个实施子阶段。

### Stage 9.0：代码基线、第三方准入与能力审计

目标：

确认当前代码、数据和第三方工具是否具备开始实施的条件。

任务：

1. 检查 Git 分支、HEAD、工作区修改、未跟踪文件和现有 worktree。
2. 检查 Stage 8 文档、候选池文件、Manifest 和数据质量报告。
3. 检查 Stage 8 实际产出的字段、候选数量、八类数据覆盖。
4. 检查 Java `pcbuild` 模块的 Offer 实体、Repository、Service 和 Controller。
5. 检查现有 Offer JSON fixture、数据库表、Flyway 迁移和 Build Snapshot。
6. 检查当前报价 10 VERIFIED / 18 MOCK 的历史状态是否仍然成立。
7. 检查 Agent `get_verified_offers` 如何消费 Java Offer API。
8. 检查真实第三方工具的 LICENSE、MCP 工具契约、实际测试情况。
9. 记录第三方工具的 LICENSE 与本期非商业研究定位（Q1），在数据来源章节留档。
10. 判断第三方详情、SKU 是否已经有实测结果。
11. 输出技术阻塞项和可以先行推进的部分。

重要：

如果当前 Git 工作区存在用户未提交修改：

- 不清理；
- 不覆盖；
- 不重置；
- 不擅自 stash；
- 不擅自 commit；
- 不修改无关文件；
- 在报告中完整列出影响范围。

第三方工具与数据来源按 Q1 定位准入，不标记 BLOCKED；但必须记录许可归属与用途限制，并在定位变化时重新评估。

产出：

`docs/pc-config/stage-9-readiness-report.md`

验收：

- 当前实际代码基线明确；
- Stage 8 数据交付状态明确；
- Java 现有 Offer 能力明确；
- 第三方许可、运行方式和测试覆盖明确；
- 供应商准入阻塞项明确；
- 未确认事实不能被包装成已确认结论。

### Stage 9.1：核心硬件优先级与映射范围治理

目标：

从 Stage 8 的候选数据中筛选首批需要获取市场商品的 P0 硬件。

任务：

1. 读取 Stage 8 发布的候选池。
2. 只从符合实际推荐资格的硬件中筛选 P0。
3. 建立 P0 / P1 / P2 的分类依据。
4. 输出八大硬件类别的候选数量。
5. 输出 P0 的具体硬件型号和硬件 ID。
6. 输出 P1/P2 的暂缓原因。
7. 找出缺少品牌、型号、关键规格或其他商品身份信息的硬件。
8. 生成稳定的 `request_item_id`。
9. 将映射任务与 `catalog_version` 绑定。
10. 生成映射任务 Manifest。
11. 输出可供第三方或人工处理的 JSONL 导出清单。

建议输出目录，最终路径应服从 Stage 8 实际数据目录规范：

```
data/pc-config/
├── exports/
│   ├── marketplace-mapping-requests.jsonl
│   └── marketplace-mapping-manifest.json
└── reports/
    └── marketplace-mapping-scope-report.json
```

映射请求建议字段：

- `request_item_id`
- `catalog_version`
- `hardware_id`
- `category`
- `brand`
- `model_name`
- `manufacturer_part_number`
- `normalized_specs`
- `search_aliases`
- `mapping_priority`

缺少的字段保持 null 或明确缺失状态，不得根据经验编造。

验收：

- P0 覆盖八个硬件类别；
- CPU/GPU/主板有足够的主流候选；
- 每条映射请求都能关联到真实硬件；
- 无重复 request ID；
- 同一个候选池版本生成的导出结果稳定；
- P1/P2 被保留，没有从主数据中删除；
- 映射优先级没有覆盖硬件生命周期和推荐资格。

### Stage 9.2：低频商品采集工作流与第三方能力验证

目标：

规划一条低频、人工主导、可记录的商品获取流程。

首期只规划和验证以下读取能力：

- `taobao_search`
- `taobao_read_item`
- `taobao_read_sku`

不要将以下工具列为首期必要依赖：

- 商品评论；
- 图片批量采集；
- 购物车；
- 加购；
- 客服消息；
- 商品下单；
- 其他写入操作。

建议的商品处理流程：

```
P0 标准硬件
    │
    ▼
搜索商品
    │
    ├── 没有结果 → NOT_FOUND
    │
    ▼
读取商品详情
    │
    ├── 型号不符 → REJECTED
    ├── 关键规格缺失 → REVIEW_REQUIRED
    │
    ▼
读取具体 SKU
    │
    ├── SKU 规格不符 → REJECTED
    ├── 价格不明确 → UNVERIFIED
    │
    ▼
导出标准商品映射
    │
    ▼
独立报价校验
```

首期先选择每个硬件类别 1–2 款进行小规模 POC，验证端到端流程后再决定扩大范围。

不要设计每分钟处理量、批量并发数或者反爬规避策略。

不能将当前工具的冷却参数理解为平台允许的最大频率或安全保证。

产出：

- 第三方能力验证计划；
- 本地采集操作说明；
- 标准结果导出格式；
- 采集失败和人工处理状态规范。

本子阶段继续使用供应商无关的输入输出契约，确保未来替换数据源时导入层无需重写；不复制第三方项目的源代码。

### Stage 9.3：商品映射、数据标准化和报价可信校验

目标：

将外部商品信息转换为本项目自己的标准商品映射和报价数据。

任务：

1. 建立标准化商品映射契约。
2. 建立标准化 Offer 导入契约。
3. 设计硬件身份匹配规则。
4. 设计商品规格校验规则。
5. 设计价格口径判断规则。
6. 设计商家身份信息校验。
7. 设计商品链接校验规则。
8. 设计报价采集时间与有效期策略。
9. 设计异常记录与隔离机制。
10. 设计商品重复匹配和 SKU 冲突处理机制。

重点检查：

**商品身份：**

- 品牌是否一致；
- 完整型号是否一致；
- 桌面 GPU 与 Laptop GPU 是否区分；
- GPU 显存规格是否一致；
- CPU 型号和后缀是否一致；
- 主板插槽、芯片组是否一致；
- 内存 DDR 类型、容量和规格是否一致；
- SSD 容量、接口、形态是否一致；
- 电源功率和规格是否一致；
- 散热器支持插槽和规格是否一致；
- 机箱板型、尺寸规格是否一致。

不能只根据搜索标题的关键词相似度将商品标记为 VERIFIED。

**价格信息：**

- 必须为 CNY；
- `price_fen` 是大于零的整数；
- `price_type` 和 `price_basis` 必须分开；
- 价格采集时间明确；
- 有效期有可靠依据；
- 会员价和优惠券价不能默认作为所有用户可获取的价格；
- `final_payable` 未确认时保持 null；
- 不允许推断最终支付金额；
- 过期数据不能进入求解器。

**异常隔离：**

以下情况不能自动转成可信报价：

- 商品型号冲突；
- SKU 规格冲突；
- 商家信息缺失；
- 平台商品 ID 不可靠；
- 价格为零或负数；
- 货币不明确；
- 价格口径无法解释；
- 购买链接无效；
- 报价有效期无法确定；
- 第三方结果无法对应到 `hardware_id`；
- 数据来源不允许商业使用。

异常记录应保存原因和来源，方便后续人工查看。

首期不建设复杂人工审核后台，可以使用 JSONL/CSV 报告和少量人工抽查流程。

### Stage 9.4：Offer 契约扩展、整份校验发布与运行时接入

目标：

按 Q2，把通过校验的真实报价以「整份 JSON 校验后发布」的方式接入 Java，不引入数据库表。

必须优先复用：

- `pc-config/offers.json` 与 `JsonOfferRepository`；
- `OfferQueryService`；
- Build Snapshot 的 `offer_snapshot jsonb`（已能保存完整报价列表，无需改表）；
- 现有 `/internal/v1/pc/offers` 与证据字段（`priceSource`、`verifiedCount`、`mockCount`）；
- 现有服务令牌鉴权与 Spring Modulith 模块边界。

不要新增 Marketplace 独立微服务，不要新增 Offer / Mapping / Import Batch 表。

#### 9.4.1 发布流程

```
采集结果 JSONL
    ↓
Schema 校验（字段、枚举、金额为分、链接格式）
    ↓
商品身份校验（型号/规格与 hardware_id 一致）
    ↓
报价可信校验（price_type、price_basis、observed_at、valid_until）
    ↓
dry-run 预览：新增 / 更新 / 拒绝 / 隔离 计数
    ↓
写同目录临时文件 offers.json.tmp
    ↓
对临时文件做全量校验
    ↓
os.replace 原子替换 offers.json
    ↓
运行 validate 与 fixture 测试
```

- 发布脚本**扩展** `scripts/pc-config/ingest_offers.py`，不新建第二套报价 ETL。该脚本已实现模板校验、`price_cny` → 整数分、`hardware_id` 必须在 catalog、`offer_id` 去重、https 链接与 PCPartPicker 链接拦截、无有效报价拒绝覆盖、`--dry-run`；本期只补字段、规则核验、TTL 与原子写入。
- 写入前必须在内存中完成全部校验；任何一条不通过则不生成临时文件，保持上一版可用。
- 落盘使用「同目录临时文件 → 全量校验 → `os.replace` 原子替换」：同卷替换是原子的，写入中断不会留下半份 JSON。回滚依赖 Git，不额外保留报价副本。
- `offers.json` 的 `catalog_version` 必须与当前硬件主数据版本一致。

#### 9.4.2 Offer record 兼容扩展

现有 `Offer` 为 16 字段 record。本期只允许**新增可空字段**，且必须同步以下位置：

| 位置 | 变更 |
| --- | --- |
| `application-service/.../pcbuild/domain/Offer.java` | 新增 `priceBasis`、`observedAt`、`provider`、`availabilityStatus`、`verificationMethod`（均可空） |
| `application-service/.../pcbuild/infrastructure/OfferFixture.java` | 增加同名 JSON 映射，缺省为 `null` |
| `application-service/.../pcbuild/web/dto/OfferResponse.java` | 增加同名字段，旧字段保持不变 |
| `docs/pc-config/api-contract.md` | 同步字段与取值 |
| `docs/pc-config/data-model.md` | 同步 `offers.json` 字段表 |
| Agent `get_verified_offers` schema | 透传新字段，不改变现有必填项 |

不得修改 `priceType` 的语义或类型，不得删除 `priceSource`。`platform` 表示电商平台（如 `TAOBAO`），`provider` 表示采集工具或数据来源（如 `chengkit-taobao`、`MANUAL`），二者不重复。`observedAt` 使用完整时间戳；现有 `verifiedAt` 为 `LocalDate`，粒度不足以表达观测时刻，但本期不改变 `verifiedAt` 的类型。

#### 9.4.3 必须修复的既有缺陷

- `Offer.isUsableOn()` 当前把 `MOCK` 视为可用；生产求解路径必须只接受 `priceSource=OWNER_VERIFIED`，新增的 `PLATFORM_OBSERVED` 同样不得进入生产求解。
- `OfferQueryService.cheapestUsableByHardware` 的 `requireVerified` 默认值必须显式化，禁止隐式选到演示价或页面观测价。
- `build_solver` 重试时强制 `require_verified_offers=false` 的行为必须移除或改为可配置，不允许静默降级。
- `candidate_retriever` 的 `verified_only=False` 必须改为配置项，生产配置下为 `true`。
- 三类来源的计数必须分离，避免用 `verifiedCount` 掩盖真实覆盖度。

#### 9.4.4 幂等与增量

- 报价唯一键：`(provider, platform, platformSku, seller, shopName)`，与 `hardware_id` 一并参与去重。
- 整份重写意味着「本次未出现的报价会被移除」；发布前必须确认采集结果覆盖上一版全部有效报价，否则按差集告警并阻止发布。
- `valid_until` 缺失时不得视为永久有效：发布脚本按 **14 天** TTL 补齐，并写入 `valid_until_derived=true` 以区分页面原始值。该 TTL 定义为脚本常量，便于后续调整。
- 首期为一次性验证，不排周期刷新；重新采集通过 `scripts/pc-config/` 下的手动入口执行，不在本期引入调度。

#### 9.4.5 数据库

本期不新增 Flyway 迁移。`pc_build_snapshots.offer_snapshot` 已能保存完整报价列表；`Offer` 新增字段会随 `OfferResponse` 进入快照，无需改表结构。

#### 9.4.6 旧报价处理（Q10）

首版 `offers.json` 目前有 10 条 `OWNER_VERIFIED`。整份重写会移除未出现在新结果中的报价，因此发布前必须：

- 逐条核对这 10 条与首批 8 款的关系；
- 与首批相关的条目复核链接与价格，仍有效的保留，并补齐 `observed_at`、`price_basis`、`provider`；
- 与首批无关的条目一律丢弃，不做「为兼容而保留」；
- 差集结果写入发布预览输出，人工确认后才允许写盘。

#### 9.4.7 `ingest_offers.py` 现有缺口

审计当前脚本后确认需要补的能力（其余逻辑直接复用）：

| 缺口 | 现状 | 本期要求 |
| --- | --- | --- |
| 新增字段 | 只输出 14 个字段 | 增加 `price_basis`、`observed_at`、`provider`、`availability_status`、`verification_method` |
| 来源分流 | `price_source` 硬编码 `OWNER_VERIFIED` | 按 §5.5 规则核验结果决定 `OWNER_VERIFIED` 或 `PLATFORM_OBSERVED` |
| 价格性质 | 非法值直接报错，无 `UNKNOWN` | 空标签映射为 `UNKNOWN`，其余非法值仍报错 |
| 有效期 | 只校验 `valid_until >= verified_at` | 额外校验未过期；缺失时按 14 天 TTL 补齐并标记推导 |
| 落盘 | `write_text` 直接覆盖 | 临时文件 + `os.replace` 原子替换 |
| 差集保护 | 模板变短会静默删除旧报价 | 发布前输出差集，未确认则拒绝写入 |

### Stage 9.5：真实报价验证、E2E 与文档收尾

目标：

证明完整商品映射与报价链路真正可用。

数据测试：

- P0 映射请求可追踪；
- 导入记录可以追溯 `hardware_id`；
- 商品 ID / SKU 与硬件型号一致；
- 同一硬件多个商品映射可以并存；
- 同一商品多个商家 Offer 可以并存；
- 重复导入幂等；
- 失效和过期 Offer 被排除；
- MOCK 不进入生产；
- 部分批次失败不会导致已有有效 Offer 被误删；
- 报价变化不修改历史 Snapshot。

求解测试：

- 八大硬件类别都有真实有效报价覆盖；
- 至少有一套配置能使用真实 Offer 完整组成；
- CPU/GPU/主板至少各有两个不同硬件型号具备有效报价，作为首期基本备选目标；
- 已知兼容性 FAIL 的组合不能进入最终方案；
- UNKNOWN 不能伪装成 PASS；
- 总价不能超过预算；
- 无有效报价时返回结构化无解原因；
- 价格更新后新配置读取新报价，旧配置保留旧报价。

E2E 场景至少包括：

1. 八件套完整推荐；
2. 某一类别缺少真实报价；
3. 商品身份不匹配；
4. SKU 规格不匹配；
5. 报价过期；
6. 商家信息缺失；
7. 多商家报价；
8. 预算不可行；
9. 第三方工具或数据源不可用；
10. 价格更新后的新旧 Snapshot 对比。

建议抽查至少 3 条报价/类别；某类别不足 3 条时全部检查。抽查数量是首期质量门槛，不代表已完成的商品数量。

文档更新：

- `docs/pc-config/market-offer-management.md`
- `docs/pc-config/data-model.md`
- `docs/pc-config/api-contract.md`
- `docs/pc-config/architecture.md`
- `docs/pc-config/testing-and-evaluation.md`
- `docs/pc-config/README.md`
- `.env.example`
- 环境变量文档
- 必要的 ADR

最终报告：

`docs/quality/pc-config-stage-9-report.md`

必须记录真实数据量、各类别覆盖率、映射成功率、有效报价率、异常数量、供应商能力、测试结果和未完成项。

---

## 八、报价覆盖率与 Stage 9 完成标准

不能以“搜索返回多少商品”作为 Stage 9 完成标准。

必须统计：

指标

定义

P0 总数

当前映射范围中 P0 硬件数量

商品映射数

已通过商品身份核验的硬件数量

SKU 核验数

已核验具体 SKU 的商品数量

有效报价硬件数

至少拥有一个有效 Offer 的硬件数量

P0 映射率

已成功映射的 P0 / P0 总数

SKU 核验率

已完成 SKU 核验的商品 / 已映射商品

有效报价率

有有效 Offer 的硬件 / 已映射硬件

八类覆盖率

具备真实有效报价的硬件类别 / 8

核心型号备选数

CPU、GPU、主板等类别拥有多少不同硬件型号有效报价

异常率

被隔离或拒绝的商品 / 已处理商品

首期目标（第一批，Q5=B；Q11 主流档，预算 7,000–9,000 元）：

1. 八个硬件类别各完成 1 款真实报价，共 8 款；
2. 这 8 款必须能组成一套完整兼容的参考配置；
3. 每款至少 1 条 `price_source=OWNER_VERIFIED` 且未过期的报价；
4. 所有进入求解器的 Offer 都经过身份和报价验证；
5. MOCK 不参与生产求解；
6. 每条报价可追溯来源、价格出处与采集时间；
7. 历史 Snapshot 不受市场报价更新影响；
8. 未获取到报价的硬件如实记录，不通过虚构数据填充。

第二批（首期链路通过后）：扩展到 16 款，即每类约 2 款，其中 CPU、GPU、主板各至少 2 个不同型号。8 款是链路验证门槛，不代表最终覆盖规模。

不得为了完成百分比而使用来源不明或未标注的数据。

---

## 九、严格控制 Stage 9 的非目标范围

以下内容明确不属于 Stage 9：

- 自建京东、淘宝、天猫爬虫；
- 开发反爬绕过方案；
- 代理池或账号/IP 轮换；
- 验证码破解；
- 复杂浏览器指纹伪装；
- 无人值守的高频批量采集；
- 将 chengkit-taobao 直接嵌入 Agent Service；
- 让 Agent 直接调用淘宝 MCP；
- 新建 Marketplace 微服务；
- 多供应商插件市场；
- 复杂人工审核后台；
- 商品价格历史分析平台；
- 自动加购、下单或支付；
- RAG；
- MCP 多 Agent 编排；
- 重写 LangGraph；
- 重做前端聊天界面；
- 重做 SSE；
- 重构与 Stage 9 无关的认证、会话和模型管理能力；
- 对所有 P1/P2 过时硬件进行全量商品映射。

后续如果确实需要，再单独规划阶段。

---

## 十、必须分析的架构和实现风险

请逐项分析：

1. chengkit-taobao 本地浏览器模式是否适合作为低频数据获取工具；
2. 该项目商业许可证对当前产品使用方式的限制；
3. 未验证的商品详情和 SKU 功能对方案的影响；
4. 淘宝商品标题中存在多个型号、容量和品牌混杂的问题；
5. SKU 价格与商品展示价不一致的问题；
6. 会员价、优惠券价和普通公开价的区别；
7. 商品链接可能失效或跳转的问题；
8. 第三方服务限流、验证码、账号限制对采集计划的影响；
9. 多次采集产生重复商品和重复 Offer 的问题；
10. 旧 VERIFIED 报价的有效性；
11. 生产 MOCK 数据隔离；
12. 商品身份变化和硬件主数据版本变化；
13. 部分批次导入失败；
14. 价格更新和 Build Snapshot 一致性；
15. Stage 8 输出格式与 Java Offer 现有契约的衔接；
16. 第三方数据来源的商业授权和存储展示授权；
17. 未来增加京东或其他供应商时的扩展性。

每个风险应标注：

- 发生条件；
- 影响范围；
- 严重程度；
- 当前是否已证实；
- 推荐处理方式；
- 是否阻塞 Stage 9。

禁止为了让方案显得完整而虚构风险概率、接口能力或第三方承诺。

---

## 十一、本轮具体工作方式：只审计和规划，不实施

这是本次任务中最重要的执行约束。

本轮请严格执行以下顺序：

### 第一步：读取当前仓库

读取：

- 根目录项目说明；
- 系统架构文档；
- `docs/pc-config/` 全部相关文档；
- Stage 8 相关数据产出；
- 数据模型；
- 市场报价管理文档；
- Java `pcbuild`；
- Agent 的报价工具；
- 现有 Offers fixture；
- Flyway 迁移；
- 相关测试。

如果某项文件不存在，应在报告中说明，不得根据历史计划假设文件已经实现。

### 第二步：检查当前工作区

记录：

- 当前分支；
- HEAD；
- `git status`；
- 未提交修改；
- 未跟踪文件；
- 相关测试当前状态；
- 已有未完成任务。

不要修改这些内容。

### 第三步：检查第三方工具

如果当前工作区没有第三方项目，不要擅自克隆、安装或执行其代码。

只分析已经提供的 GitHub 地址和实测报告。

实际执行 POC 需要负责人单独授权，并按 Q1 的非商业研究定位留档。

### 第四步：输出完整 Stage 9 规划

在全部审计后，将实际项目状态与本提示词的目标进行对照，输出完整实施计划。

每个子阶段必须列出：

1. 阶段目标；
2. 当前依赖；
3. 已具备能力；
4. 现存差距；
5. 具体任务；
6. 预计修改的目录和文件；
7. 是否需要新增数据库表或迁移（Q2 已定：本期不新增）；
8. 数据契约变化；
9. 测试计划；
10. 验收标准；
11. 风险；
12. 阻塞项；
13. 是否能够独立实施；
14. 前置阶段完成条件。

文件路径必须来自当前仓库审计，不要照抄模板路径后就声称文件存在。

### 第五步：输出实施批次安排

将 Stage 9 拆成便于 Coding Agent 执行的批次。

每个批次应当：

- 范围明确；
- 依赖明确；
- 有可测试的交付物；
- 可以独立检查；
- 不和其他批次重复修改同一业务职责；
- 不涉及不必要的全局重构。

建议至少包括：

- 批次 A：代码基线、许可和能力准入；
- 批次 B：P0 优先级治理和映射请求导出；
- 批次 C：第三方商品数据适配和标准化；
- 批次 D：商品身份、报价验证与隔离；
- 批次 E：Java 导入、数据库和 OfferRepository 接入；
- 批次 F：真实报价 E2E 和文档收尾。

根据真实审计结果，可以调整批次数量和先后顺序，但不能删除上述核心职责。

---

## 十二、最终交付物与输出格式

本轮必须产出以下内容：

### 12.1 审计报告

`docs/pc-config/stage-9-readiness-report.md`

内容包括：

- 当前仓库基线；
- Stage 8 完成情况；
- Java Offer 能力；
- Agent 调用链；
- 数据现状；
- 第三方工具情况；
- 许可与合规判断；
- 未验证能力；
- 现有技术阻塞项。

### 12.2 Stage 9 完整实施计划

`docs/pc-config/stage-9-plan.md`

需要覆盖 Stage 9.0–9.5 的完整任务拆分、架构、数据契约、实施批次、验收标准和风险。

### 12.3 Stage 9 状态跟踪

建议创建：

`docs/pc-config/stage-9-checklist.md`

需要包含：

- 阶段状态；
- 任务状态；
- 依赖；
- 阻塞原因；
- 验收结果；
- 后续实施入口。

### 12.4 最终总结

完成审计后在最终回复中提供：

1. 当前真实项目基线；
2. Stage 8 对 Stage 9 的实际准备程度；
3. 第三方工具是否具备准入条件；
4. P0/P1/P2 的实际硬件分布；
5. 推荐的数据模型；
6. 商品数据采集及导入架构；
7. Stage 9 完整执行顺序；
8. 每个批次的具体任务；
9. 预计涉及的代码与文档范围；
10. 数据库变更建议；
11. 测试与验收标准；
12. 尚未解决的风险和阻塞项。

### 12.5 不能做的事情

- 不修改现有 Java、Python、React 业务代码；
- 不修改数据库；
- 不执行 Flyway；
- 不批量修改 Stage 8 数据；
- 不执行真实淘宝采集；
- 不增加新的电商爬虫；
- 不复制第三方项目的源代码；抓取或解析的数据必须标注来源；
- 不修改 Agent Graph；
- 不修改 SSE 契约；
- 不重构与 Stage 9 无关的功能；
- 不提交 Git；
- 不清理用户现有未提交修改。

本轮只允许新增上述 Stage 9 规划与审计文档，不允许借机修改现有项目实现。

---

## 十三、最终决策原则

遇到不确定内容时，按照以下优先级处理：

1. 当前源码和真实测试结果；
2. 当前 Stage 8 数据与文档；
3. 当前项目已有架构决策；
4. 第三方公开文档和正式许可；
5. 项目负责人提供的实测报告；
6. 本提示词中的规划建议。

如果不同来源冲突，必须指出冲突，不能擅自选择对实现最方便的一种解释。

如果第三方能力没有实测，不得标记为已支持。

如果第三方许可未确认，不得标记为可以商业集成。

如果 Stage 8 数据资产未交付，不得假装能够导出真实 P0 清单。

如果八大类数据覆盖不足，不得通过 MOCK 数据制造完整覆盖。

如果某款硬件没有可靠商品报价，允许暂时无法推荐该硬件。

**宁可减少商品覆盖率，也不能牺牲商品身份、报价真实性和用户预算准确性。**

本次任务的最终目标不是让数据量看起来很大，而是为后续 Stage 9 的实际开发建立一份与当前仓库完全匹配、范围明确、可以逐批执行和验收的实施计划。

现在开始审计和规划，不要开始业务代码实施。
