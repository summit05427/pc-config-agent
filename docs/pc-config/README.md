# PC 配置模块文档集

| 项 | 内容 |
| --- | --- |
| 适用范围 | `docs/pc-config/` 的入口与索引；PC 配置模块的 Agent、Java、数据与评测文档 |
| 状态 | Current |
| 最后更新 | 2026-11-17 |
| 权威性 | 本文件只做导航；阶段状态与遗留问题以 [roadmap](../planning/roadmap.md) 为准，接口契约以 [docs/api-contract.md](../api-contract.md) §5.7、§7 为准 |

## 1. 当前基线（2026-11-17 核验）

- **选型**：Agent 侧 LLM 在 `build_architect` 输出 `BuildProposal`；Java 只提供候选、跑分、报价、组装、兼容校验与快照，不提供求解接口。
- **图**：9 个节点（7 个业务节点 + 2 个 HITL 门控），见 [Agent 工作流](../services/agent-service/agent-workflows.md)。
- **兼容规则**：9 条，全部 `BLOCKING`，见 [compatibility-rules.md](./compatibility-rules.md)。
- **数据**：目录 402 款；报价 402 条，全部 `PLATFORM_OBSERVED`，无 `OWNER_VERIFIED`；跑分 169 条。
- **默认模型**：`deepseek:deepseek-flash`（网关 `model_name` 同名）。
- **未实现**：多 Agent、RAG 知识库均处于规划中。

## 2. 文档导航

| 文档 | 职责 |
| --- | --- |
| [architecture.md](./architecture.md) | 三端职责、调用链、LLM 选型与事实权威的边界 |
| [compatibility-rules.md](./compatibility-rules.md) | 9 条兼容规则的唯一详细说明 |
| [data.md](./data.md) | 运行时夹具、快照表、数据质量与治理产物 |
| [market-offer-management.md](./market-offer-management.md) | 报价来源、平台观测价与核验升级流程 |
| [testing-and-evaluation.md](./testing-and-evaluation.md) | 测试矩阵、评测命令与回归基线 |
| [glossary.md](./glossary.md) | 领域术语与中文命名 |
| [README.md](./README.md) | 本文档集入口 |

Agent 节点、状态、工具与 HITL 的详细说明统一放在 [services/agent-service/agent-workflows.md](../services/agent-service/agent-workflows.md)，本目录不再维护第二份。

## 3. SSOT 分工

| 事实 | 唯一维护位置 |
| --- | --- |
| 选型决策权与事实权威边界 | [architecture.md](./architecture.md) §2 |
| 9 条兼容规则 | [compatibility-rules.md](./compatibility-rules.md) |
| 接口路径、字段、错误码、`done.build_result` | [docs/api-contract.md](../api-contract.md) §5.7、§7 |
| 环境变量与默认值 | [docs/deployment/environment-variables.md](../deployment/environment-variables.md) |
| 阶段状态与遗留问题 | [docs/planning/roadmap.md](../planning/roadmap.md) |
| 离线治理批次与分布 | [硬件主数据治理报告](../quality/hardware-data-governance-report.md) |

## 4. 读者路径

- **产品 / 验收**：先读 [roadmap](../planning/roadmap.md) §2 与 §6。
- **Agent 开发**：[architecture.md](./architecture.md) → [agent-workflows.md](../services/agent-service/agent-workflows.md) → [compatibility-rules.md](./compatibility-rules.md)。
- **Java 后端**：[architecture.md](./architecture.md) → [compatibility-rules.md](./compatibility-rules.md) → [data.md](./data.md)。
- **数据维护**：[market-offer-management.md](./market-offer-management.md) → [data.md](./data.md) → [治理报告](../quality/hardware-data-governance-report.md)。
- **评测**：[testing-and-evaluation.md](./testing-and-evaluation.md)。

> 未在代码中出现的能力一律标注「规划中」或「未实现」，不提前承诺。
