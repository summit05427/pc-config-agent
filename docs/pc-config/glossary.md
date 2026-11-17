# PC 配置领域术语

| 项 | 内容 |
| --- | --- |
| 适用范围 | PC 配置模块的领域语言与中文命名 |
| 状态 | Current |
| 最后更新 | 2026-11-17 |
| 权威性 | 本文只定义概念，不描述实现；跨端通用术语见 [docs/README.md](../README.md) §3 与根 `GLOSSARY.md` |

## 1. 数据与商品

**硬件（Hardware）**：具有唯一 `hardware_id`、类别、品牌、型号与规格的标准实体。它是跑分与商品的挂载点，不等同于任何平台商品。避免说「商品」「SKU」。

**候选硬件（Candidate Hardware）**：本轮交给 LLM 的硬件子集，来自 Java 候选接口；只在本次推荐内有效。避免说「库存」。

**跑分（Benchmark）**：硬件在特定基准下的性能记录，含类型、分数、来源与匹配置信度。它是性能代理指标，不等于实际帧率或专业软件得分。

**商品 / 报价（Marketplace Offer）**：某硬件在某个平台上的销售记录，含平台、商家、标题、人民币分价、链接、来源与有效期。同一硬件可有多条。

**价格来源（Price Source）**：`OWNER_VERIFIED`（人工核验）、`PLATFORM_OBSERVED`（平台观测/参考价）、`MOCK_DEMO`（演示占位价）。只有 `OWNER_VERIFIED` 计入已核验报价。

**核验报价（Verified Quote）**：`price_source=OWNER_VERIFIED` 且报价可用的商品价格。当前运行时没有核验报价。

## 2. 方案与流程

**配置方案（PC Build）**：恰好包含 CPU、主板、内存、显卡、电源、机箱、散热、存储各一件的完整组合，用 `build_id` 标识。

**方案提案（Build Proposal）**：Agent LLM 输出的 8 类 `hardware_id` 组合，尚未经 Java 组装校验。它与配置方案不是同一实体。

**配置结果（Build Result）**：Java `compose` 成功后的方案，含总价、预算状态、兼容性报告、跑分快照、报价快照与逐件理由。它是渲染层的唯一结构化输入。

**配置快照（Build Snapshot）**：配置结果在创建时刻的不可变副本，写入 `pc_build_snapshots`，只追加不更新。

**选型决策权（Selection Authority）**：决定「选哪一个 `hardware_id`」的权力，归 Agent 侧 LLM；只覆盖取舍，不含事实判定。

**事实权威（Fact Authority）**：对型号、规格、跑分、报价、链接、预算与兼容性结论的最终判定权，归 Java。选型方只能引用，不能改写。

**配置策略（Build Strategy）**：`build_strategist` 产出的方向性建议，含策略标识、预算倾向、组件优先级与取舍原则；不给出具体型号或金额。

**兼容性报告（Compatibility Report）**：逐条记录 9 条规则结论的结构化报告，状态为 `PASS` / `WARNING` / `FAIL` / `UNKNOWN`。`UNKNOWN` 不得当作通过。

**预算状态（Budget Status）**：`WITHIN_BUDGET` 或 `NO_BUDGET`；超预算直接失败，不返回方案。

**澄清（Clarification）**：结构化需求缺少关键信息时的追问状态，不是无解也不是错误。

**工作流状态（Workflow Status）**：图当前阶段结果，取值为 `parsed` / `clarification` / `invalid` / `validated` / `retrieved` / `no_candidates` / `success` / `retry` / `architect_failed` / `aborted` / `upstream_error`。

**结构化失败（Structured Failure）**：`build_failure` 中的失败类型、阶段与可修正标记；用于驱动 `build_architect` 的有限修正，不直接展示给用户。

**工具事件（Tool Event）**：节点累积的工具调用进度，由 `turn.py` 翻译成 `tool_call` / `tool_result`；不包含工具原始输出。

**无解（Infeasible）**：在硬约束下不存在可用完整配置。无解必须返回结构化原因，不得放宽预算、删除类别或编造价格。

## 3. 数据治理

**数据质量状态（Data Quality Status）**：`VERIFIED_STRUCTURED` / `PARTIAL` / `BLOCKED`，标记规格是否完整。关键字段缺失时相关兼容规则返回 `UNKNOWN`。

**治理状态（Governance Status）**：离线治理结论，`VALID` / `INCOMPLETE` / `INVALID` / `CONFLICT`。

**生命周期状态（Lifecycle Status）**：`CURRENT` / `MATURE` / `LEGACY` / `DISCONTINUED` / `UNKNOWN`。`UNKNOWN` 不代表不可推荐。

**市场状态（Market Status）**：`AVAILABLE` / `UNVERIFIED` / `EOL`；未核验不得写成可购。

**推荐资格（Recommendation Status）**：`ELIGIBLE` / `RESTRICTED` / `EXCLUDED` / `ARCHIVED`，由类别规则派生，与生命周期不是等价关系。

**发布候选池（Published Pool）**：离线治理按生命周期与推荐资格生成的持久化清单，分 standard / budget / legacy / archived 四类；尚未接入运行时。

**硬件主数据（Hardware Master）**：经标准化治理的硬件全集，用 `hardware_id` 标识；不含价格与购买链接。

**匹配范围（Match Scope）**：跑分与硬件的关联粒度，`ITEM` 或 `CHIPSET`。显卡按芯片级共享跑分，不得表述为单卡实测分。
