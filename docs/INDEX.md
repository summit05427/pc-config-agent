# 任务索引（最小必读入口）

| 项 | 内容 |
| --- | --- |
| 状态 | Current |
| 最后核验 | 2026-11-08 |
| 用途 | 按任务给出最小必读清单，避免加载无关文档与整目录浏览 |

**读取规则**：先查本表命中任务 → 只读「必读」列出的 1–3 份 → 用 Grep 定位章节后按 offset/limit 读取命中段。禁止整目录读取。

## 1. 任务路由

| 任务 | 必读（按顺序） | 补充（仅命中细节时读） |
| --- | --- | --- |
| 改前端页面 / 组件 / 样式 | `frontend/CODEMAP.md` → `docs/services/frontend/development-guide.md` → `docs/services/frontend/ui-quick-reference.md` | `ui-design-system.md` 对应章节 |
| 改前端接口调用 / SSE | `docs/api-contract-quick-reference.md` → `docs/services/frontend/development-guide.md` | `api-contract.md` 对应端点、`generative-ui.md` |
| 改管理端 | `admin/CODEMAP.md` → `docs/services/admin/development-guide.md` → `docs/services/admin/architecture.md` | `docs/api-contract-quick-reference.md` |
| 改 Java 接口 / 业务 | `.trae/rules-on-demand/20-backend-java.md` → `application-service/CODEMAP.md` → `docs/services/application-service/architecture.md` | `api-reference.md` 对应端点、`security.md` |
| 改 Agent 节点 / 工具 / 流式 | `.trae/rules-on-demand/30-agent-python.md` → `agent-service/CODEMAP.md` → `docs/services/agent-service/agent-workflows.md` | `api-reference.md`、`model-runtime-architecture.md` |
| 改 PC 配置需求解析 / 求解 / 推荐 | `docs/pc-config/README.md` → `docs/pc-config/agent-workflow.md` → `docs/pc-config/solver-and-compatibility.md` | `agent-state-and-tools.md`、`data-model.md`、`docs/api-contract.md` §5.7 |
| 改报价数据 / 核验报价 | `docs/pc-config/market-offer-management.md` → `docs/pc-config/data-quality-and-lifecycle.md` | `docs/pc-config/offers.template.json`、`scripts/pc-config/ingest_offers.py` |
| 硬件主数据治理 / 生命周期分类 / 发布候选池 | `docs/quality/hardware-data-governance-report.md` → `data/pc-config/README.md` | `docs/planning/Stage8.md`、`docs/adr/0013`–`0017`、`docs/pc-config/data-quality-and-lifecycle.md` §8 |
| 跨端契约变更 | `docs/development-rules.md` §1 → `docs/api-contract-quick-reference.md` | `docs/api-contract.md` 全文 |
| 环境变量 / 部署 / 排障 | `docs/deployment/env-quick-reference.md` | `deployment-guide.md`、`environment-variables.md` |
| Solo（只跑 Agent，dev-token 体验） | `docs/deployment/solo-mode.md` | `deployment-guide.md` §3.3 |
| 模型运行时 / BYOK | `docs/model-runtime-architecture.md` | `docs/services/application-service/api-reference.md` |
| OpenUI 生成式 UI | `docs/services/frontend/generative-ui.md` | `docs/api-contract.md` §7.1、`docs/services/frontend/ui-design-system.md` |
| 文档一致性 / 治理 | `docs/documentation-governance.md` | `docs/README.md` |
| 企业级达标自检 / 对外介绍前评估 | `docs/quality/enterprise-readiness.md` | `docs/architecture-overview.md` §7、`docs/planning/closure-plan.md` |
| 看当前待办 / 收尾与放行条件 | `docs/planning/closure-plan.md` | — |
| Agent 模板遗留 / 边界 / 已完成事项依据 | `docs/planning/closure-plan.md` | `docs/adr/0004-extension-config-file-first.md`、`0005-agent-profile-first-class.md`、`0006-mechanism-vs-content-boundary.md` |
| 第一次接触项目 | `docs/architecture-overview.md` → 所在端 `CODEMAP.md` | `docs/README.md` 全量清单 |

## 2. 规则文件路由

| 改动范围 | 规则文件 |
| --- | --- |
| `frontend/**` | `.trae/rules-on-demand/10-frontend.md` |
| `admin/**` | `.trae/rules-on-demand/40-admin.md` |
| `application-service/**` | `.trae/rules-on-demand/20-backend-java.md` |
| `agent-service/**` | `.trae/rules-on-demand/30-agent-python.md` |
| 全仓库通用 | `.trae/rules/00-monorepo-common.md`（常驻注入，无需重复读取） |

## 3. 派生文档说明

`docs/api-contract-quick-reference.md`、`docs/services/frontend/ui-quick-reference.md`、`docs/deployment/env-quick-reference.md` 是速查派生视图：与源文件冲突时以源文件为准，源文件变更时同步更新这三份。
