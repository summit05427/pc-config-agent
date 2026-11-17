# 任务索引（最小必读入口）

| 项 | 内容 |
| --- | --- |
| 状态 | Current |
| 最后更新 | 2026-11-17 |
| 用途 | 按任务给出最小必读清单，避免加载无关文档与整目录浏览 |

**读取规则**：先查本表命中任务 → 只读「必读」列出的 1–3 份 → 用 Grep 定位章节后按 offset/limit 读取命中段。禁止整目录读取。

## 1. 任务路由

| 任务 | 必读（按顺序） | 补充（仅命中细节时读） |
| --- | --- | --- |
| 第一次接触项目 | [architecture-overview.md](architecture-overview.md) → 所在端 `CODEMAP.md` | [README.md](README.md) 全量清单 |
| 改前端页面 / 组件 / 样式 | `frontend/CODEMAP.md` → [frontend/development-guide.md](services/frontend/development-guide.md) → [frontend/ui-quick-reference.md](services/frontend/ui-quick-reference.md) | [ui-design-system.md](services/frontend/ui-design-system.md) |
| 改前端接口调用 / SSE | [api-contract-quick-reference.md](api-contract-quick-reference.md) → [frontend/development-guide.md](services/frontend/development-guide.md) | [api-contract.md](api-contract.md) 对应端点、[generative-ui.md](services/frontend/generative-ui.md) |
| 改管理端 | `admin/CODEMAP.md` → [admin/development-guide.md](services/admin/development-guide.md) → [admin/architecture.md](services/admin/architecture.md) | [api-contract-quick-reference.md](api-contract-quick-reference.md) |
| 改 Java 接口 / 业务 | `.trae/rules-on-demand/20-backend-java.md` → `application-service/CODEMAP.md` → [application-service/architecture.md](services/application-service/architecture.md) | [api-reference.md](services/application-service/api-reference.md)、[security.md](services/application-service/security.md) |
| 改 Agent 节点 / 工具 / 流式 | `.trae/rules-on-demand/30-agent-python.md` → `agent-service/CODEMAP.md` → [agent-workflows.md](services/agent-service/agent-workflows.md) | [agent-service/architecture.md](services/agent-service/architecture.md)、[api-reference.md](services/agent-service/api-reference.md) |
| 改 PC 配置需求解析 / 选型 / 推荐 | [pc-config/README.md](pc-config/README.md) → [agent-workflows.md](services/agent-service/agent-workflows.md) → [compatibility-rules.md](pc-config/compatibility-rules.md) | [pc-config/architecture.md](pc-config/architecture.md)、[data.md](pc-config/data.md) |
| 查兼容性规则 / UNKNOWN 语义 | [compatibility-rules.md](pc-config/compatibility-rules.md) | [api-contract.md](api-contract.md) §5.7 |
| 改候选、报价、跑分、快照数据 | [pc-config/data.md](pc-config/data.md) → [pc-config/market-offer-management.md](pc-config/market-offer-management.md) | [hardware-data-governance-report.md](quality/hardware-data-governance-report.md) |
| 硬件主数据治理 / 发布候选池 | [hardware-data-governance-report.md](quality/hardware-data-governance-report.md) → [pc-config/data.md](pc-config/data.md) §10 | [adr/0027-pc-config-decisions.md](adr/0027-pc-config-decisions.md) §3 |
| 评测 / 回归 / 真实模型验证 | [pc-config/testing-and-evaluation.md](pc-config/testing-and-evaluation.md) | `agent-service/evals/`、[agent-workflows.md](services/agent-service/agent-workflows.md) §13 |
| 跨端契约变更 | [development-rules.md](development-rules.md) §1 → [api-contract.md](api-contract.md) | [api-contract-quick-reference.md](api-contract-quick-reference.md) |
| 环境变量 / 部署 / 排障 | [deployment/env-quick-reference.md](deployment/env-quick-reference.md) | [deployment/environment-variables.md](deployment/environment-variables.md)、[deployment/deployment-guide.md](deployment/deployment-guide.md) |
| Solo（只跑 Agent，dev-token 体验） | [deployment/solo-mode.md](deployment/solo-mode.md) | [deployment/deployment-guide.md](deployment/deployment-guide.md) §3.3 |
| 模型运行时 / BYOK | [model-runtime-architecture.md](model-runtime-architecture.md) | [api-reference.md](services/application-service/api-reference.md) |
| OpenUI 生成式 UI | [generative-ui.md](services/frontend/generative-ui.md) | [api-contract.md](api-contract.md) §7.1、[ui-design-system.md](services/frontend/ui-design-system.md) |
| 文档一致性 / 治理 | [documentation-governance.md](documentation-governance.md) | [README.md](README.md) |
| 看阶段状态 / 当前待办 / 遗留问题 | [roadmap.md](planning/roadmap.md) §5 | — |
| 了解选型权迁移方案 | [pc-config-agent-refactor-plan-v1.md](planning/pc-config-agent-refactor-plan-v1.md) | [adr/0028-llm-led-build-selection.md](adr/0028-llm-led-build-selection.md) |

## 2. 规则文件路由

| 改动范围 | 规则文件 |
| --- | --- |
| `frontend/**` | `.trae/rules-on-demand/10-frontend.md` |
| `admin/**` | `.trae/rules-on-demand/40-admin.md` |
| `application-service/**` | `.trae/rules-on-demand/20-backend-java.md` |
| `agent-service/**` | `.trae/rules-on-demand/30-agent-python.md` |
| 全仓库通用 | `.trae/rules/00-monorepo-common.md`（常驻注入，无需重复读取） |

## 3. 派生文档说明

[api-contract-quick-reference.md](api-contract-quick-reference.md)、[ui-quick-reference.md](services/frontend/ui-quick-reference.md)、[env-quick-reference.md](deployment/env-quick-reference.md) 是速查派生视图：与源文件冲突时以源文件为准，源文件变更时同步更新这三份。
