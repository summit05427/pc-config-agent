# PC 配置智能推荐 Agent 路线图（Stage 1–11）

| 项 | 内容 |
| --- | --- |
| 状态 | Current |
| 最后核验 | 2026-11-11 |
| 权威性 | 本文件取代 `docs/planning/planning.md`、`Stage8.md`、`Stage9.md`、`Stage10.md`、`Stage11.md` 与 `closure-plan.md`，是阶段目标、已确认决策、当前状态与遗留问题的唯一入口 |
| 实测口径 | 文中所有「实测」数字均由 2026-11-11 本机命令复现，方法与命令见 §9；未复现的历史结论标注为「报告记载」 |
| 关联文档 | [系统架构](../architecture-overview.md)、[PC 配置模块](../pc-config/README.md)、[API 契约](../api-contract.md)、[ADR](../adr/)、[质量报告](../quality/) |

## 1. 产品定位与不变量

### 1.1 目标

面向 PC 装机场景的 LLM Agent：用户用自然语言描述预算与用途，系统给出预算内、兼容、可解释的八件套配置，并保留可回放的决策快照。项目定位为本地化、封闭式、非商业学术研究（[ADR 0027](../adr/0027-pc-config-decisions.md) §2.3），第三方商品数据只做研究用途并保留来源追溯。

### 1.2 四端职责

| 端 | 技术栈 | 职责 |
| --- | --- | --- |
| `frontend` | React 19 + TypeScript | 需求输入、SSE 消费、配置结果卡片、HITL 表单 |
| `admin` | React 19 + shadcn-admin | 用户、反馈、模型目录与定价 |
| `application-service` | Java 21 + Spring Boot + Modulith | 硬数据、兼容性、求解、预算、快照与报价的**唯一业务权威** |
| `agent-service` | Python 3.12 + FastAPI + LangGraph | 需求解析、确定性单图编排、解释生成、HITL |

依赖方向固定：浏览器 → Nginx → `application-service` / `agent-service`；Agent 只可调用 Java `/internal/v1/**`，Java 不调用 Agent。

### 1.3 不可协商的红线

1. 兼容性判断、求解、报价查询与快照由 Java 负责；Agent 与 LLM 不得重算或改写结果。
2. 求解确定性：同一输入 + 同一规则版本产生稳定结果；价格为整数分。
3. 不伪造硬件规格、价格与商品链接；无法确认一律 `UNKNOWN`，`UNKNOWN` 不等于 `PASS`，也不自动等于 `FAIL`。
4. `MOCK_DEMO` 报价不得进入生产求解，也不得表述为已核验。
5. 历史 `BuildSnapshot` 不可变，规则升级与价格更新不得改写历史配置。
6. 不新增独立 Solver 微服务，不引入与当前阶段无关的 RAG / Multi-Agent / MCP Server。

## 2. 当前基线（2026-11-11 实测）

### 2.1 运行时数据

| 项 | 实测值 | 位置 |
| --- | --- | --- |
| 硬件目录 | **402** 款（CPU 71 / GPU 66 / 主板 60 / 内存 60 / 存储 53 / 电源 40 / 机箱 26 / 散热 26） | `application-service/src/main/resources/pc-config/catalog.json` |
| 报价 | **402** 条，全部 `PLATFORM_OBSERVED`（无人工作业核验价） | `application-service/src/main/resources/pc-config/offers.json` |
| 报价覆盖 | 402 个不同 `hardware_id`，与目录一一对应，无孤儿、无缺价 | 同上 |
| 报价元数据 | `data_status=PLATFORM_OBSERVED_ONLY`、`catalog_version=2026.11.2`、`observed_offer_count=159` | 同上 |
| 跑分 | `benchmarks.json` 共 **169** 条 `entries`（CPU 71 / GPU 66 / 存储 32），另有 21 条 `unmatched` | `application-service/.../benchmarks.json` |

### 2.2 离线治理产物

| 产物 | 实测行数 | 说明 |
| --- | --- | --- |
| `data/pc-config/master/hardware-master.jsonl` | 8,238 | 全量主数据，`raw_specs` 保留原始行 |
| `data/pc-config/master/hardware-benchmarks.jsonl` | 3,557 | PassMark 映射：MATCHED 1,942 / UNMATCHED 1,610 / AMBIGUOUS 5 |
| `data/pc-config/staging/duplicates.jsonl` | 2,203 | BRAND_MODEL 1,148 / MODEL_SIGNATURE 1,052 / MPN 3 |
| `data/pc-config/staging/conflicts.jsonl` | 473 | 人工审核队列，未自动合并 |
| `data/pc-config/pools/*.jsonl` | standard 4,107 / budget 7,200 / legacy 1,197 / archived 142 | 每行是单件硬件，不是完整配置 |
| `data/pc-config/export/marketplace/*.jsonl` | matches 23,771 / listings 889 / llm_splits 2 | Stage 9 商品映射中间产物 |
| `data/pc-config/manifest/catalog-manifest.json` | `catalog_version=2026.11.0`、`distribution_status=INTERNAL_ONLY` | 离线产物版本与运行时 `catalog_version` 为两条独立版本流 |

### 2.3 版本与门禁

- 规则版本：`pc-solver-2.1.0`、`pc-compat-2.0.0`、`pc-scoring-1.0.0`。
- 治理结论：`governance_status` VALID 6,954 / INCOMPLETE 1,284；`lifecycle_status` UNKNOWN 2,782、MATURE 2,319、CURRENT 1,798、LEGACY 1,197、DISCONTINUED 142；`recommendation_status` ELIGIBLE 7,263、RESTRICTED 833、EXCLUDED 142。

## 3. Stage 1–6：基础交付（已完成）

| 阶段 | 交付 | 状态 |
| --- | --- | --- |
| Stage 1 | 数据收敛与字段归一化、PassMark 匹配、中国区报价录入 | 完成（后续由 Stage 8/9 扩展） |
| Stage 2 | Java `pcbuild` 模块、七类内部接口、V24 快照表 | 完成 |
| Stage 3 | Agent 确定性单图替换通用 ReAct 图 | 完成（[ADR 0027](../adr/0027-pc-config-decisions.md) §1.1） |
| Stage 4 | 前端 PC 入口与 `BuildResultCard` | 完成 |
| Stage 5 | 端到端联调与指标核对 | 完成，证据见 [联调报告](../quality/pc-config-e2e-2026-11.md) |
| Stage 6 | `docs/pc-config/` 文档集与根文档同步 | 完成，本文件已按现状收敛 |

历史方案中的 28 款候选、28 条报价、8 条跑分是 Stage 1–5 的基线，已被 Stage 9 的数据扩充覆盖，不得再作为当前事实引用。

## 4. Stage 8：硬件主数据治理

### 4.1 目标

把 8,238 条 PCPartPicker 硬件与 25,318 条 PassMark 跑分加工为可追溯、可分级、可重复生成的硬件主数据，输出候选池与第三方映射输入清单。本期**不接入 Java 运行时**。

### 4.2 已确认决策

| 项 | 决策 |
| --- | --- |
| 产物位置 | `data/pc-config/`，JSONL 为权威，Parquet 仅派生；原始数据外部只读 |
| 运行时边界 | 不改 Repository / Solver / Agent / 前端；价值是标准化资产 |
| 状态字段 | 保留 `data_quality_status` 原语义，新增独立 `governance_status`；生命周期、市场、推荐资格各自独立 |
| 生命周期 | 分类别分阶段推进；`UNKNOWN` 不等于 `EXCLUDED` |
| ETL | 原地演进 `scripts/pc-config/`，禁止第二套流水线；脚本测试纳入 CI |
| 许可 | 未核实前 `distribution_status=INTERNAL_ONLY`，全量产物不进版本库 |

对应 [ADR 0027](../adr/0027-pc-config-decisions.md) §3。

### 4.3 实测结果

- 主数据 8,238 条；`governance_status` 以 VALID 为主（6,954），INCOMPLETE 1,284。
- 生命周期 UNKNOWN 2,782 条（33.8%），集中在散热器、机箱、电源等无可靠发布日期的类别，符合「允许 UNKNOWN」的决策。
- 跑分映射 3,557 行，GPU 为芯片级多对一（`match_scope=CHIPSET`，1,109 行），存储按型号+容量匹配（DISK_MARK 1,485 行）。
- 重复候选 2,203 条、冲突 473 条仍待人工审核，未自动合并。
- 四个候选池均已生成，`scripts/pc-config/tests` 实测 118 例全绿。

### 4.4 遗留问题（实测）

| 编号 | 问题 | 实测证据 | 影响 |
| --- | --- | --- | --- |
| S8-01 | 跑分映射 UNMATCHED 1,610 行（45.3%），另有 AMBIGUOUS 5 行 | `hardware-benchmarks.jsonl` 计数 | 预算池按性能分层时大量硬件无可用跑分 |
| S8-02 | 冲突 473 条、重复候选 2,203 条未消费 | `staging/*.jsonl` 行数 | 同一实体可能以多条主数据存在 |
| S8-03 | 离线产物 `catalog_version=2026.11.0` 与运行时 `2026-11-09-reference-12` 无映射说明 | 两份 manifest | 无法从线上配置反查治理批次 |
| S8-04 | 主数据 8,238 条与运行时目录 3,974 款无显式筛选清单 | 两处计数 | 无法复现「哪些主数据被 Stage 9 选中」 |

## 5. Stage 9：商品映射与真实报价

### 5.1 目标

以淘宝为首期数据源，把可售硬件映射到真实商品与报价，保证进入求解器的报价可追溯、未过期，并保持文件型 `offers.json` 发布形态（[ADR 0027](../adr/0027-pc-config-decisions.md) §2.1）。

### 5.2 已确认决策（Q1–Q19 摘要）

| 主题 | 决策 |
| --- | --- |
| 定位与合规 | 非商业研究；`chengkit-taobao` 不标 BLOCKED，数据可入库，来源与追溯必须保留 |
| 存储形态 | 继续 `classpath:pc-config/offers.json` + `JsonOfferRepository`，不建 Offer/映射表、不加迁移 |
| 平台 | 首期淘宝；京东为备选 |
| 范围 | 先 P0 核心硬件，按清洗后的 `sellable` 集合采集，不按 8,238 条全量分配预算 |
| 价格来源 | 新增 `PLATFORM_OBSERVED`；规则核验通过才升 `OWNER_VERIFIED`；生产求解只接受 `OWNER_VERIFIED` |
| 价格口径 | 详情页 `ITEM_DETAIL` 为主，`SKU_PANEL` 为回退，`SEARCH_LIST` 只用于定位；金额为整数分，禁止汇率与折扣推算 |
| 新增字段 | `price_basis`、`observed_at`、`provider`、`availability_status`、`verification_method`，全部可空 |
| 有效期 | 缺失按 14 天 TTL 补齐；刷新为手动入口 |
| 核验 | 取消人工逐条核对，改为确定性规则；不通过一律保持 `PLATFORM_OBSERVED` |
| 发布 | 临时文件 → 全量校验 → `os.replace` 原子替换，回滚靠 Git |
| 首期门槛 | 八类各 1 款、可组成一套完整兼容配置、每款至少 1 条未过期 `OWNER_VERIFIED` |

对应 [ADR 0027](../adr/0027-pc-config-decisions.md) §2。

### 5.3 实测结果

- 报价已扩到 3,837 条，八类均有覆盖：内存 1,065、机箱 825、散热 592、主板 512、电源 369、GPU 206、存储 197、CPU 71。
- `OWNER_VERIFIED` 仅 10 条（CPU 4 / GPU 4 / 主板 2），其余为 `PLATFORM_OBSERVED` 3,809 条与 `MOCK_DEMO` 18 条。
- 商品映射中间产物：`matches.jsonl` 23,771 行、`listings.jsonl` 889 行。
- 发布脚本、规则核验、fallback 定价与原子发布脚本均已在 `scripts/pc-config/` 落地。

### 5.4 遗留问题（实测）

| 编号 | 问题 | 实测证据 | 影响 |
| --- | --- | --- | --- |
| S9-01 | **价格口径违反 Q18**：`FALLBACK` 2,474 条、`BUCKET` 1,139 条、`SEARCH_LIST` 167 条，合计 3,780 条不是详情页或 SKU 面板价，却以 `PLATFORM_OBSERVED` 进入 `offers.json` | `offers.json` 按 `price_basis` 计数 | 生产求解会把粗档中位价当作观测价使用 |
| S9-02 | `availability_status` 3,809 条全为 `UNKNOWN`，没有一条 `AVAILABLE` | 同上 | 无法排除下架商品；Availability 规则只能 UNKNOWN |
| S9-03 | `valid_until` 空值 3,827 条，未按 Q9 补 14 天 TTL | 同上 | 报价永不过期，与「未过期报价」门槛冲突 |
| S9-04 | `MOCK_DEMO` 18 条仍在 `offers.json`；`data_status` 仍为 `MIXED_DEMO` | 计数与 `data_status` | 18 条演示价可能参与求解；前端对所有结果显示演示价提示 |
| S9-05 | Stage 9 约定的五个字段未进入 Java `Offer` record，`requireVerifiedOffers` 默认 `false` | `pcbuild/domain/Offer.java`、`OfferQueryService` | 运行时无法按 `OWNER_VERIFIED` 或 `availability_status` 过滤 |
| S9-06 | 144 款目录硬件无任何报价；GPU 仅 206/289 有报价 | 目录与报价计数 | 部分显卡无法进入标准池，求解可能退化为无解 |
| S9-07 | `data_status=OWNER_VERIFIED` 从未出现 | `offers.json` 元数据 | 放行条件 G-05 无法满足 |

## 6. Stage 10：求解器与兼容性引擎

### 6.1 目标

在现有确定性 `BuildSolver` 上补齐兼容性规则、用途画像、搜索剪枝、结果解释与快照依据，不重写稳定模块。

### 6.2 已完成

- 兼容性规则统一为九条，全部 `risk_level=BLOCKING`（[ADR 0027](../adr/0027-pc-config-decisions.md) §4.4）；新增 `memory_module_count`。
- 六值 `WorkloadProfile`（GENERAL / GAMING / VIDEO_EDITING / PROGRAMMING / RENDERING / AI_INFERENCE）+ 渲染取向 + 澄清。
- 用途感知排序、兼容感知池构建、`preference` 性价比分支、确定性兜底。
- `componentReasons` + `reasonSummary`；评分版本写入快照 JSON，无新增迁移（[ADR 0027](../adr/0027-pc-config-decisions.md) §4.2）。
- 合同步：Java DTO、Agent Schema、前端类型、`docs/api-contract.md` 已对齐。

### 6.3 实测结果

- `BuildSolverTests` **19/19 通过**（当前 3,974 款目录下）。
- 兼容性数据覆盖率（`catalog.json`）：

| 字段 | 覆盖 | 后果 |
| --- | --- | --- |
| 机箱 `max_gpu_length_mm` | 822/822 | 可判定 |
| 机箱 `max_cooler_height_mm` | **0/822** | 散热器-机箱限高规则恒为 UNKNOWN |
| 机箱 `radiator_support` | **0/822** | 水冷冷排安装规则恒为 UNKNOWN |
| 主板 `max_memory` | **0/512** | 内存容量上限规则恒为 UNKNOWN |
| 散热器 `height_mm` | 422/589 | 28% 记录限高 UNKNOWN |
| 散热器 `radiator_size_mm` | 116/589 | 水冷规则大面积 UNKNOWN |
| 电源 `pcie_12vhpwr_count` | 284/368 | 新显卡供电接口规则部分 UNKNOWN |
| GPU `external_power` | 285/289 | 基本可判定 |

### 6.4 遗留问题（实测）

| 编号 | 问题 | 实测证据 | 影响 |
| --- | --- | --- | --- |
| S10-01 | 机箱限高、冷排支持、主板最大内存三类关键字段为 0 覆盖 | §6.3 统计 | 九条 BLOCKING 规则中有三条只能返回 UNKNOWN，默认方案持续显示「待核验」 |
| S10-02 | 芯片组 CPU 支持、BIOS 版本、VRM、QVL、M.2 通道共享仍无字段 | 目录规格键清单 | 只能 UNKNOWN，无法兑现任务书的 PASS/FAIL 判定 |
| S10-03 | `mvnw verify` 本次未完成：`AdminFeedbackApiTests` 认证审计写入 `MyBatisSystemException` 后长时间阻塞 | 运行日志与线程栈 | 无法据此判定 Java 全量门禁通过；该测试不在 `pcbuild` 包 |
| S10-04 | 性能基线结论来自上一轮（兼容感知池构建约 3.6 倍搜索成本），本轮未重跑 | 历史报告 | 目录扩到 3,974 后性能数字可能已变化 |

## 7. Stage 11：Agent 工程化能力

### 7.1 范围裁定

| 子阶段 | 结论 |
| --- | --- |
| 11.1 Evaluation / Observability / Guardrails / Context / Reliability | 收口完成：节点级追踪、输出事实校验、上下文裁剪、幂等与并发锁、Prometheus 指标 |
| 11.2 RAG | **暂缓**：无官方 PDF / 手册 / QVL 语料，只有可插拔接缝 |
| 11.3 HITL | **完成**：interrupt/resume、SSE 事件、前端表单、权限与过期、恢复测试 |
| 11.4 Memory | 暂缓独立记忆，复用 Java 用户偏好 |
| 11.5 MCP | 已是 MCP 客户端（默认关闭），不对外暴露 Server（[ADR 0027](../adr/0027-pc-config-decisions.md) §5） |
| 11.6 Multi-Agent | `DEFERRED`：确定性单图 + Java 求解已覆盖 |
| 11.7 集成验收 | 非 RAG 路径完成 |

### 7.2 实测结果

- `hitl.py`、`output_guard.py`、`node_tracing.py`、`mcp.py`、`rag/base.py`、`hitl-prompt.tsx` 均存在。
- `evals/` 仅 2 个用例文件，回归规模仍小。
- Agent 静态检查：`ruff` 通过、`mypy` 82 个源文件无问题。
- 前端 `type-check` 通过。

### 7.3 遗留问题（实测）

| 编号 | 问题 | 实测证据 | 影响 |
| --- | --- | --- | --- |
| S11-01 | `pytest` **2 例失败、1 例跳过**（592 passed） | `uv --directory agent-service run pytest -q` | 门禁未全绿 |
| S11-02 | 失败点一：`test_success_path_renders_deterministic_markdown` 仍断言 `## 推荐配置`，实际输出已改为 OpenUI 块 | 失败断言 | 渲染器已迁移，测试未同步 |
| S11-03 | 失败点二：`test_clarification_without_hitl_keeps_original_flow` 在 HITL 关闭时仍被澄清门中断 | 失败断言 | 无 HITL 流程出现行为回归 |
| S11-04 | RAG 无进展 | `rag/base.py` + `RAG__ENABLED=false` | 知识类问题仍无法引用权威来源 |
| S11-05 | 评估集仅 2 个用例文件 | `evals/` 文件计数 | 回归覆盖不足，难以支撑「评估体系」结论 |

## 8. 跨阶段遗留问题总表

按「是否影响数据诚信 / 生产可用 / 门禁」排序。所有条目均有 §9 的实测证据。

| 优先级 | 编号 | 问题 | 下一步 |
| --- | --- | --- | --- |
| P0 | S9-01 | 3,780 条非详情页价格以 `PLATFORM_OBSERVED` 发布 | 要么改标 `price_basis` 并禁止进入求解，要么补齐详情页价 |
| P0 | S9-05 | 五个报价字段未进 Java 模型，默认接受非核验报价 | 扩展 `Offer` record 与过滤条件，或显式拒绝非 `OWNER_VERIFIED` |
| P0 | S9-04 | 18 条 `MOCK_DEMO` 仍在生产文件；`data_status` 仍 `MIXED_DEMO` | 清退演示价，按实际来源重算 `data_status` |
| P0 | S9-03 | 3,827 条报价无 `valid_until` | 补 14 天 TTL 或标 `UNKNOWN` 并拒绝参与求解 |
| P1 | S9-02 | 3,809 条 `availability_status=UNKNOWN` | 采集侧补可得性，或在求解前过滤 |
| P1 | S10-01 | 机箱限高、冷排、主板最大内存 0 覆盖 | 补数据或把规则降级为 `ADVISORY` 并明示 |
| P1 | S11-01/02/03 | Agent 2 例失败 | 同步 OpenUI 断言；修复 HITL 关闭时的澄清行为 |
| P1 | S8-01 | 跑分 UNMATCHED 45.3% | 扩展匹配规则，禁止用估算分补位 |
| P1 | S8-02 | 473 条冲突未审核 | 建立人工审核批次与结论记录 |
| P2 | S8-03/04 | 离线与运行时版本无映射 | 在 manifest 中登记运行时目录筛选清单 |
| P2 | S10-03 | 全量 `mvnw verify` 未跑通 | 定位 `AdminFeedbackApiTests` 的测试库审计写入问题 |
| P2 | S10-04 | 性能基线未复测 | 目录扩充后重跑基准并记录剪枝量 |
| P2 | S11-04/05 | RAG 暂缓、评估集过小 | 语料到位后另立阶段；先扩评估用例 |

### 8.1 文档规范与实际决策的冲突

| 冲突 | 规范/决策怎么写 | 实际是什么 | 本轮处理 |
| --- | --- | --- | --- |
| 报价口径 | Stage 9 Q18：只允许详情页或 SKU 面板价进入生产 | 3,780 条 `FALLBACK`/`BUCKET`/`SEARCH_LIST` 以 `PLATFORM_OBSERVED` 发布 | 不改数据，登记为 P0（S9-01） |
| 兼容规则等级 | Stage 10：九条规则全部 `BLOCKING` | 机箱限高、冷排、主板最大内存三个字段 0 覆盖，规则只能 UNKNOWN | 保留决策，登记为 P1（S10-01） |
| 文档删除策略 | `docs/README.md` 原规则：归档优先于删除 | 本次要求合并后删除 Stage 8–11 任务书 | 已修订规范：被权威文档完整承接且引用清零后可删除，历史由 Git 保留 |
| 数据规模表述 | `pc-config/README.md` 与 [ADR 0027](../adr/0027-pc-config-decisions.md) §4.5：28 款 / 234 款 | 3,974 款 / 3,837 条 | 已改为实测口径并标注历史基线 |
| 计划文档归属 | `documentation-governance.md` D-06：待办收敛为 closure-plan | closure-plan 本身已过期且与 Stage 任务书重复 | 统一为 `roadmap.md` |

## 9. 实测方法与命令（2026-11-11）

```powershell
# 数据规模与分布
python -m pytest scripts/pc-config/tests -q          # 118 passed
uv --directory agent-service run ruff check app tests evals run.py
uv --directory agent-service run mypy                 # 82 files, no issues
uv --directory agent-service run pytest -q            # 592 passed, 2 failed, 1 skipped
corepack pnpm --dir frontend type-check               # 通过
cd application-service; .\mvnw.cmd -o test "-Dtest=BuildSolverTests" "-Djacoco.skip=true"   # 19 passed
powershell -File scripts/check-doc-links.ps1          # 2026-11-11 修复前 2 处断链

# 报价与目录统计（PowerShell + ConvertFrom-Json / Python json）
# 目录：3,974 款；报价：3,837 条；price_basis / availability / valid_until 计数见 §5.4
# 治理产物：master 8,238 / benchmarks 3,557 / duplicates 2,203 / conflicts 473
```

未完成项：`mvnw verify` 全量在 `AdminFeedbackApiTests` 处阻塞，已终止，未据此判定通过或失败；前端 `test:coverage`、`e2e:critical` 本轮未重跑。

## 10. 下一阶段边界

Stage 12 的候选范围（尚未排期）：

1. 报价可信度收口：S9-01/03/04/05，决定「观测价」能否进入求解。
2. 兼容性数据补齐：机箱限高/冷排、主板最大内存、BIOS/QVL/M.2 通道共享。
3. RAG：先解决语料来源与许可，再评估 pgvector 检索。
4. 评估体系扩容：把当前 2 个用例文件扩到可回归规模。

明确不做：多方案对比、瓶颈分析、交互式硬件替换、自动购买、价格历史与监控后台、Multi-Agent、MCP Server、独立 Solver 微服务、前端聊天架构重写。
