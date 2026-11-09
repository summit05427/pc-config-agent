# PC 配置模块文档集

| 项 | 内容 |
| --- | --- |
| 状态 | Completed（Stage 1–6 完成；Stage 8 离线数据治理完成，待 Stage 9 接入运行时） |
| 最后核验 | 2026-11-09 |
| 权威性 | 本文件是 `docs/pc-config/` 的入口与 SSOT 索引；术语、HTTP/SSE 契约与环境变量不在本文件重复定义 |
| 主要证据 | [实施计划](../planning/pc-config-implementation-plan.md)、[联调报告](../quality/pc-config-e2e-2026-11.md)、`agent-service/app/agent/pc/`、`application-service/.../pcbuild/**` |

## 1. 当前状态摘要

- **数据**：`catalog.json` 28 款硬件（CPU 4 / GPU 4 / 主板 4 / 内存 4 / 存储 3 / 散热 3 / 机箱 3 / 电源 3）；`offers.json` 28 条（10 条 `OWNER_VERIFIED` + 18 条 `MOCK_DEMO`），`dataStatus=MIXED_DEMO`；`benchmarks.json` 8 条聚合跑分。
- **阶段**：Stage 1 数据、Stage 2 Java `pcbuild`、Stage 3 Agent 单图、Stage 4 前端卡片、Stage 5 联调、Stage 6 文档集与根文档同步均已完成。
- **实测结论**（2026-11-08）：15000 元 GAMING 生成 8 件配置、总价 146.42 万分的方案；3000 元返回无解且不放宽预算；缺预算与用途时只追问。证据见 [联调报告](../quality/pc-config-e2e-2026-11.md)。
- **数据治理**（2026-11-09）：`data/pc-config/` 已生成 8,238 条硬件主数据、3,557 行跑分映射、四类发布候选池与 8,096 条第三方映射输入；**尚未接入运行时**，在线推荐覆盖率本期不变。详见 [硬件主数据治理报告](../quality/hardware-data-governance-report.md)。

## 2. 文档集导航

按 [实施计划 §6.1](../planning/pc-config-implementation-plan.md) 共 12 份，已全部交付：

| 文档 | 一句话职责 | 状态 |
| --- | --- | --- |
| [README.md](./README.md) | 文档集入口、当前状态与 SSOT 索引 | 已交付 |
| [demo-scope.md](./demo-scope.md) | 本期演示范围、不做清单与数据诚信红线 | 已交付 |
| [architecture.md](./architecture.md) | 三端职责、调用链与确定性单图的设计理由 | 已交付 |
| [agent-workflow.md](./agent-workflow.md) | 六节点、条件路由、重解与 SSE 事件映射 | 已交付 |
| [agent-state-and-tools.md](./agent-state-and-tools.md) | 图状态字段、checkpointer、5 个工具与 Profile | 已交付 |
| [data-model.md](./data-model.md) | 硬件、跑分、报价、配置快照的数据结构与字段来源 | 已交付 |
| [data-quality-and-lifecycle.md](./data-quality-and-lifecycle.md) | 数据质量状态、生命周期与推荐可用性规则 | 已交付 |
| [market-offer-management.md](./market-offer-management.md) | 人工核验报价的录入、校验与替换流程 | 已交付 |
| [solver-and-compatibility.md](./solver-and-compatibility.md) | 求解搜索、预算剪枝与 8 条兼容性规则 | 已交付 |
| [api-contract.md](./api-contract.md) | PC 内部接口与 `done.build_result` 的模块级说明 | 已交付 |
| [testing-and-evaluation.md](./testing-and-evaluation.md) | 测试矩阵、评测用例与回归基线 | 已交付 |
| [extension-roadmap.md](./extension-roadmap.md) | 数据替换、候选扩充与后续演进的边界 | 已交付 |

## 3. SSOT 分工

| 事实 | 唯一维护位置 |
| --- | --- |
| 领域术语与中文命名 | [glossary.md](./glossary.md) |
| 对外 HTTP / SSE 契约、内部接口路径 | [docs/api-contract.md](../api-contract.md) §5.7、§7 |
| 环境变量名、默认值与生产校验 | [docs/deployment/environment-variables.md](../deployment/environment-variables.md) |
| 阶段任务与验收指标 | [docs/planning/pc-config-implementation-plan.md](../planning/pc-config-implementation-plan.md) §5、§8 |
| 联调证据与遗留问题 | [docs/quality/pc-config-e2e-2026-11.md](../quality/pc-config-e2e-2026-11.md) |
| 治理产物、发布批次与生命周期分布 | [硬件主数据治理报告](../quality/hardware-data-governance-report.md)、`data/pc-config/manifest/catalog-manifest.json` |

## 4. 读者路径

- **产品 / 验收**：先读 [demo-scope.md](./demo-scope.md)，再按计划 §8 与联调报告核对指标。
- **Java 后端**：读 [solver-and-compatibility.md](./solver-and-compatibility.md) 与 [data-model.md](./data-model.md)，契约以 [api-contract.md](../api-contract.md) §5.7 为准。
- **Agent 开发**：按 [architecture.md](./architecture.md) → [agent-workflow.md](./agent-workflow.md) → [agent-state-and-tools.md](./agent-state-and-tools.md) 顺序阅读。
- **前端**：读 [architecture.md](./architecture.md) 的调用链，并核对 [api-contract.md](../api-contract.md) §7 的 `done.build_result`。
- **数据维护**：读 [candidate-shortlist.md](./candidate-shortlist.md)、[market-offer-management.md](./market-offer-management.md) 与 [data-quality-and-lifecycle.md](./data-quality-and-lifecycle.md)。

> 本目录中的实现描述以当前分支源码为准；未在代码中出现的能力一律标注【未实现】，不提前承诺。
