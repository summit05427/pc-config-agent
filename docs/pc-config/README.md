# PC 配置模块文档集

| 项 | 内容 |
| --- | --- |
| 状态 | Current |
| 最后核验 | 2026-11-12 |
| 权威性 | 本文件是 `docs/pc-config/` 的入口与索引；阶段状态与遗留问题以 [roadmap](../planning/roadmap.md) 为准，术语、HTTP/SSE 契约与环境变量不在本文件重复定义 |
| 主要证据 | [roadmap](../planning/roadmap.md)、[联调报告](../quality/pc-config-e2e-2026-11.md)、`agent-service/app/agent/pc/`、`application-service/.../pcbuild/**` |

## 1. 当前状态摘要（2026-11-12 实测）

- **数据规模**：`catalog.json` **402** 款（CPU 71 / GPU 66 / 主板 60 / 内存 60 / 存储 53 / 电源 40 / 机箱 26 / 散热 26）；`offers.json` **402** 条，与 catalog 一一对应，`data_status=PLATFORM_OBSERVED_ONLY`（无人工逐件核验价）；`benchmarks.json` 169 条（CPU 71 / GPU 66 / 存储 32）。
- **阶段状态**：Stage 1–6 完成；Stage 8 离线治理产物已生成但未接入运行时；Stage 9 商品映射与报价扩充已落地，可信度口径仍有 P0 缺口；Stage 10 兼容规则、用途画像、排序与解释已实施；Stage 11 HITL 与可观测性完成，RAG 暂缓。2026-11-12 起运行时目录改由 `scripts/data-cleaning` 流水线产出。
- **实测结论**：`BuildSolverTests` 19/19 通过；`scripts/pc-config/tests` 118 例通过；Agent `pytest` 592 通过、2 失败、1 跳过。
- **遗留问题**：按优先级见 [roadmap §8](../planning/roadmap.md)，本文件不复制结论。

## 2. 文档集导航

| 文档 | 一句话职责 |
| --- | --- |
| [architecture.md](./architecture.md) | 三端职责、调用链与确定性单图的设计理由 |
| [agent.md](./agent.md) | 八节点、条件路由、状态、工具、Profile 与 HITL |
| [data.md](./data.md) | 硬件、跑分、报价、快照、数据质量与治理产物 |
| [market-offer-management.md](./market-offer-management.md) | 报价录入、规则核验、原子发布与回滚 |
| [solver-and-compatibility.md](./solver-and-compatibility.md) | 求解搜索、预算剪枝、用途画像与兼容性规则 |
| [api-contract.md](./api-contract.md) | PC 内部接口与 `done.build_result` 的模块级说明 |
| [testing-and-evaluation.md](./testing-and-evaluation.md) | 测试矩阵、评测用例与回归基线 |
| [glossary.md](./glossary.md) | 领域术语与中文命名 |
| [README.md](./README.md) | 文档集入口与索引 |

## 3. SSOT 分工

| 事实 | 唯一维护位置 |
| --- | --- |
| 阶段状态、决策与遗留问题 | [docs/planning/roadmap.md](../planning/roadmap.md) |
| 领域术语与中文命名 | [glossary.md](./glossary.md) |
| 对外 HTTP / SSE 契约、内部接口路径 | [docs/api-contract.md](../api-contract.md) §5.7、§7 |
| 环境变量名、默认值与生产校验 | [docs/deployment/environment-variables.md](../deployment/environment-variables.md) |
| 联调证据 | [docs/quality/pc-config-e2e-2026-11.md](../quality/pc-config-e2e-2026-11.md) |
| 治理产物、发布批次与生命周期分布 | [硬件主数据治理报告](../quality/hardware-data-governance-report.md)、`data/pc-config/manifest/catalog-manifest.json` |

## 4. 读者路径

- **产品 / 验收**：先读 [roadmap](../planning/roadmap.md) §2 与 §8，再按联调报告核对指标。
- **Java 后端**：读 [solver-and-compatibility.md](./solver-and-compatibility.md) 与 [data.md](./data.md)，契约以 [api-contract.md](../api-contract.md) §5.7 为准。
- **Agent 开发**：按 [architecture.md](./architecture.md) → [agent.md](./agent.md) 顺序阅读。
- **前端**：读 [architecture.md](./architecture.md) 的调用链，并核对 [api-contract.md](../api-contract.md) §7 的 `done.build_result`。
- **数据维护**：读 [market-offer-management.md](./market-offer-management.md) 与 [data.md](./data.md)，采集优先级与遗留缺口见 [roadmap](../planning/roadmap.md) §4–§5。

> 本目录以当前分支源码为准；未在代码中出现的能力一律标注【未实现】，不提前承诺。
