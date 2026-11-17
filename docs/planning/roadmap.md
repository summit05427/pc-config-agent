# PC 配置智能推荐路线图

| 项 | 内容 |
| --- | --- |
| 适用范围 | PC 配置模块的阶段目标、当前状态、遗留问题与下一阶段边界 |
| 状态 | Current |
| 最后更新 | 2026-11-17 |
| 权威性 | 本文是阶段状态与遗留问题的唯一入口；接口契约见 [api-contract.md](../api-contract.md)，模块架构见 [pc-config/architecture.md](../pc-config/architecture.md) |

## 1. 产品定位与不变量

面向 PC 装机场景的 LLM Agent：用户用自然语言描述预算与用途，系统给出预算内、兼容、可解释的八件套配置，并保留可回放快照。

不可协商的红线：

1. 选型由 Agent 侧 LLM 完成，Java 只做事实权威；LLM 不得改写价格、型号、链接与兼容结论。
2. 报价、总价与预算比较一律使用整数分；超预算不得放宽。
3. 不伪造规格、价格与链接；无法确认一律 `UNKNOWN`，`UNKNOWN` 不等于 `PASS`。
4. `MOCK_DEMO` 与 `PLATFORM_OBSERVED` 不得表述为已核验。
5. 历史快照不可变。
6. 不引入独立 Solver 微服务；RAG 与多 Agent 未达可用前不得写成现有能力（RAG 代码已落地一版但默认关闭，离线评测集未建）。

## 2. 当前基线（2026-11-17 核验）

| 项 | 值 | 位置 |
| --- | --- | --- |
| 硬件目录 | 402 款（CPU 71 / GPU 66 / 主板 60 / 内存 60 / 存储 53 / 电源 40 / 机箱 26 / 散热 26） | `application-service/src/main/resources/pc-config/catalog.json` |
| 报价 | 402 条，全部 `PLATFORM_OBSERVED`，无 `OWNER_VERIFIED` | `.../offers.json` |
| 报价覆盖 | 402 个 `hardware_id`，与目录一一对应 | 同上 |
| 跑分 | 169 条（CPU 71 / GPU 66 / 存储 32），另有 21 条 unmatched | `.../benchmarks.json` |
| 默认模型 | `deepseek:deepseek-flash` | `agent-service/app/core/config.py`、`application.yaml` |
| 兼容规则 | 9 条，`pc-compat-2.0.0` | `CompatibilityRule.java` |
| Java 组装链 | `compose` / `validate` / `validate-partial` / 快照读取 | `PcBuildInternalController.java` |

## 3. 阶段状态

| 阶段 | 交付 | 状态 |
| --- | --- | --- |
| Stage 1 | 数据收敛、字段归一化、跑分匹配 | 完成 |
| Stage 2 | Java `pcbuild` 模块、内部接口、V24 快照表 | 完成 |
| Stage 3 | Agent 确定性单图替换 ReAct | 完成 |
| Stage 4 | 前端 PC 入口与 `BuildResultCard` | 完成 |
| Stage 5 | 端到端联调 | 完成；证据已由当前代码与测试取代，历史报告已删除 |
| Stage 6 | 文档集与根文档同步 | 完成，本文件为唯一状态入口 |
| Stage 8 | 离线硬件主数据治理 | 产物已生成，**未接入运行时** |
| Stage 9 | 商品映射与平台观测价 | 已落地 402 条 `PLATFORM_OBSERVED`，仍无人工核验价 |
| Stage 10 | 兼容规则、用途画像与解释 | 完成；9 条规则全部 `BLOCKING` |
| Stage 11 | HITL、可观测、护栏、评测 | HITL 与评测入口完成；RAG 检索链路已落地、默认关闭（缺 embedding 部署与外部语料） |
| Stage 12 | LLM 主导选型（`build_architect`） | 完成；旧求解器路径已删除 |
| Stage 13 | RAG 知识库与多 Agent | **部分落地**（RAG 检索已实现、默认关闭；多 Agent 规划中） |

## 4. 已确认决策

| 主题 | 决策 |
| --- | --- |
| 选型权 | 归 Agent LLM，只允许在候选集内选 `hardware_id` |
| 事实权威 | 候选、跑分、报价、组装、兼容、预算、快照归 Java |
| 工作流 | 固定 9 节点确定性图 + 2 个 HITL 门控 |
| 报价形态 | 继续使用 `classpath:pc-config/offers.json`，不建报价表 |
| 价格来源 | `OWNER_VERIFIED` / `PLATFORM_OBSERVED` / `MOCK_DEMO` 三值，统计按来源计数 |
| 兼容状态 | `PASS` / `WARNING` / `FAIL` / `UNKNOWN`，`UNKNOWN` 必须显式展示 |
| 模型 | 默认 `deepseek:deepseek-flash`；网关 `model_name` 同名 |
| RAG / 多 Agent | RAG 检索已落地一版（Hybrid，默认关闭，缺 embedding 部署与外部语料）；多 Agent 规划中；未达可用前不得写成现有能力 |

## 5. 遗留问题

| 优先级 | 问题 | 证据 | 影响 |
| --- | --- | --- | --- |
| P0 | 无 `OWNER_VERIFIED` 报价，全部为平台观测价 | `offers.json` 计数 | 用户侧只能看到参考价，不能宣称已核验 |
| P0 | 部分平台观测价来自估算/档位回退，未逐件核验 | `stage4-price-observations.jsonl` | 价格可信度需持续复核 |
| P1 | 机箱限高缺失：26 款中 20 款无 `max_cooler_height_mm` | `catalog.json` 统计 | `cooler_case_height` 常为 `UNKNOWN`，方案汇总为「待核验」 |
| P1 | 散热高度缺失：26 款中 11 款无 `height_mm` | 同上 | 同上 |
| P1 | 平台观测价无人工日期与有效期差异 | `offers.json` | 过期判断依赖生成脚本 |
| P1 | `verified_offer_count` 与 `demoOfferCount` 口径不同 | `BuildResult.java`、SSE 投影 | 前端提示需逐件来源优先 |
| P2 | 离线治理产物与运行时目录无映射清单 | `catalog-manifest.json` | 无法从线上配置反查治理批次 |
| P2 | 治理主数据 8,238 条未接入运行时 | `data/pc-config/` | 候选池扩容需另建链路 |
| P2 | RAG 离线评测集未建、外部语料与 rerank 未完成；多 Agent 未实现 | `app/rag/knowledge/`、`evals/` | 复杂取舍仍缺权威依据，RAG 无法验收 |
| P2 | 评测集规模小，`--real` 未进 CI | `evals/cases/` | 语义回归依赖人工 |

## 6. 下一阶段边界

1. **报价可信度收口**：补人工核验价，明确 `PLATFORM_OBSERVED` 的展示与过滤口径。
2. **兼容数据补齐**：机箱限高、散热高度、主板内存上限等字段。
3. **RAG 收口**：pgvector Hybrid 检索已落地、默认关闭；先补 embedding 部署与语料来源/许可，再建检索命中率与引用正确性离线评测集，之后评估 rerank 与 QVL/手册引用。
4. **多 Agent（规划中）**：在单图稳定后再评估 Specialist / Critic 拆分。

明确不做：独立 Solver 微服务、自动购买、价格监控后台、前端聊天架构重写、把未实现能力写进对外介绍。

## 7. 相关文档

- 模块入口：[pc-config/README.md](../pc-config/README.md)
- 兼容规则：[compatibility-rules.md](../pc-config/compatibility-rules.md)
- Agent 工作流：[agent-workflows.md](../services/agent-service/agent-workflows.md)
- 数据与报价：[data.md](../pc-config/data.md)、[market-offer-management.md](../pc-config/market-offer-management.md)
- 评测：[testing-and-evaluation.md](../pc-config/testing-and-evaluation.md)
