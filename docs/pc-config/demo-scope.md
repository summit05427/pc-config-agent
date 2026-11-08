# PC 配置演示范围

| 项 | 内容 |
| --- | --- |
| 状态 | 已完成（Stage 5 验收范围内） |
| 最后核验 | 2026-11-08 |
| 权威性 | 本文件定义本期演示的边界与数据诚信红线；阶段任务与指标以[实施计划](../planning/pc-config-implementation-plan.md)为准 |
| 主要证据 | [联调报告](../quality/pc-config-e2e-2026-11.md)、[候选清单](./candidate-shortlist.md)、`application-service/src/main/resources/pc-config/*.json` |

术语（候选硬件、配置方案、核验报价、无解等）统一见 [glossary.md](./glossary.md)，本文件不再重复定义。

## 1. 本期用户与目标

- **用户**：登录后的普通用户，从唯一聊天入口用自然语言描述装机需求。
- **目标**：把需求转成恰好包含 8 类硬件的一套完整配置，给出总价、预算状态、兼容性结论与可点击的购买链接。
- **成功标准**：方案可解释、可复现；不超预算、不编造价格与链接、不把未验证规格说成已兼容。

## 2. 本期范围

### 2.1 硬件与数据

- **8 类硬件**：CPU、主板、内存、显卡、电源、机箱、散热器、存储，每类恰好一件。
- **平台覆盖**：CPU 覆盖 AMD AM5 与 Intel LGA1851；显卡覆盖 NVIDIA 与 AMD。
- **数据规模**：28 款候选（CPU 4 / GPU 4 / 主板 4 / 内存 4 / 存储 3 / 散热 3 / 机箱 3 / 电源 3），来自 `catalog.json`；候选明细见 [candidate-shortlist.md](./candidate-shortlist.md)。
- **报价规模**：28 条，其中 10 条 `OWNER_VERIFIED`、18 条 `MOCK_DEMO`，整体 `dataStatus=MIXED_DEMO`。
- **跑分**：8 条聚合跑分（`benchmarks.json`）。

### 2.2 场景

- Java 求解器支持 6 类场景：`GAMING`、`CREATIVE`、`PROGRAMMING`、`WORKSTATION`、`OFFICE`、`BALANCED`。
- Agent 解析层当前只产出 4 类：`GAMING`、`CREATIVE`、`OFFICE`、`BALANCED`；`PROGRAMMING`、`WORKSTATION` 仅能由直接调用 Java 内部接口传入【未实现】。
- `VIDEO_EDITING`、`GENERAL_USE` 由 Java 分别归一化为 `CREATIVE`、`BALANCED`，不新增枚举。

### 2.3 交互形态

- **完整配置而非整机**：只输出 8 件配件组合，不提供整机商品、装机服务或外设。
- **澄清**：预算与用途都缺失时先追问，不替用户假设。
- **无解**：预算不足或组合不可行时返回结构化原因与最低可行预算，不放宽预算、不删减类别。

## 3. 明确不做

- 全量 8,238 条 PCD 数据清洗与导入。
- 商品自动采集、爬虫、电商 API、自动 SKU 匹配。
- 硬件数据版本化与历史价格曲线。
- OR-Tools 等外部求解器。
- RAG、MCP、HITL、多 Agent 编排。
- 多方案对比、瓶颈分析、交互式硬件替换。
- 管理端硬件 / 商品维护页面。
- OpenUI 生成式配置卡片。

## 4. 数据诚信红线

1. `MOCK_DEMO` 报价不得表述为「已核验」「真实在售」；正文与卡片必须显式标注「演示价格」。
2. 兼容性 `UNKNOWN` 不得表述为「通过」；缺失规格（如机箱散热限高）必须如实提示未验证。
3. 不得编造价格、商品链接、商家或核验时间；链接只能来自 Java 结构化结果。
4. 不得为了凑出方案而放宽预算、删除硬件类别或忽略已知 `FAIL`。
5. 工具失败不得伪装成正常推荐，必须走确定性失败文案。

## 5. 验收指标

本期验收以[实施计划 §8](../planning/pc-config-implementation-plan.md)为准，核心项包括：成功配置恰好 8 类、严格预算超支为 0、已知硬性兼容冲突进入成功方案为 0、虚构链接与价格均为 0、未验证规格不得展示为已兼容。实测结果与证据见[联调报告](../quality/pc-config-e2e-2026-11.md)。
