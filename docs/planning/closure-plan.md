# 收尾计划：当前待办与放行条件

| 项 | 内容 |
| --- | --- |
| 状态 | Current |
| 最后核验 | 2026-11-10 |
| 权威性 | Authoritative（当前待办与放行条件的唯一入口） |
| 主要证据 | `.github/workflows/ci.yml`、各服务测试报告、[pc-config-e2e-2026-11.md](../quality/pc-config-e2e-2026-11.md)、[pc-config-implementation-plan.md](./pc-config-implementation-plan.md) |

本文件只回答两件事：**现在还有什么没做完**、**满足什么条件可以放行**。已实现的机制与设计原因不在本文展开，按需读对应文档。

## 1. 放行条件

| 编号 | 条件 | 验证方式 |
| --- | --- | --- |
| G-01 | 四端门禁全绿：前端 `lint:ci` / `type-check` / `test:coverage` / `e2e:critical`；管理端 `lint:ci` / `type-check` / `test` / `build`；Java `mvnw verify`；Agent `ruff` / `mypy` / `pytest` | CI 按路径分流执行，见 `.github/workflows/ci.yml` |
| G-02 | 文档门禁通过：`scripts/check-doc-links.ps1` 与 `scripts/check-env-docs.ps1` 零失败 | 本地或 CI 直接运行 |
| G-03 | 跨端契约一致：Java DTO、Agent Schema、前端类型、`docs/api-contract.md` 四处同步 | 人工评审 + 契约测试 |
| G-04 | 数据诚信：`MOCK_DEMO` 报价未被表述为已核验；兼容性 `UNKNOWN` 未被表述为通过 | [pc-config-e2e-2026-11.md](../quality/pc-config-e2e-2026-11.md) §4 |
| G-05 | 真实报价覆盖率达标：`data_status=OWNER_VERIFIED` 时不得残留 `MOCK_DEMO` | `scripts/pc-config/ingest_offers.py` 输出的三个计数 |

## 2. 未完成清单

| 编号 | 优先级 | 事项 | 影响面 | 完成标准 |
| --- | --- | --- | --- | --- |
| P0-01 | 高 | 用真实自营/官方旗舰店报价替换 18 条 `MOCK_DEMO` | `docs/pc-config/offers.template.json` → `offers.json` | 重跑 `ingest_offers.py` 后 `mock_offer_count=0`、`data_status=OWNER_VERIFIED` |
| P0-02 | 高 | 机箱补齐 `max_cooler_height_mm`，消除 `cooler_case_height=UNKNOWN` | `catalog.json`、兼容性报告 | 求解结果中该规则不再出现 `UNKNOWN` |
| P1-01 | 中 | 扩充入门级与高端候选，覆盖 8000 元及以下档位 | `catalog.json`、`offers.template.json` | 8000 元办公档可求解，且不放宽求解规则 |
| P1-04 | 中 | `BuildSolverTests` 6 例 + `PcBuildApiTests` 1 例断言绑定具体目录条目（硬编码 64GB 内存、合成 GPU 必胜、低预算必然无解），Stage 9 目录扩充后失效 | `application-service/src/test/java/com/example/agent/pcbuild/{BuildSolverTests,PcBuildApiTests}.java` | 断言改为不绑定具体条目（如「容量不低于下限」），或在测试内注入隔离夹具；`mvnw verify` 恢复全绿 |
| P2-01 | 低 | 报价自动采集与比价 | 数据管线 | 仅评估，不在本期实现 |
| P2-02 | 低 | 硬件版本化与历史价格曲线 | `catalog.json`、快照 | 仅评估，不在本期实现 |

## 3. 已关闭事项

| 编号 | 事项 | 关闭依据 |
| --- | --- | --- |
| R1 | P-01 Java 调用 Agent 的方向争议 | ADR-0001，保持前端直连 Agent |
| R2 | 分页默认值不一致 | 三端统一 20，前端按场景显式覆盖 |
| R3 | `/metrics` 鉴权 | Nginx 白名单 + `METRICS__TOKEN` 兜底 |
| R4 | OpenUI 提示词漂移 | `openui:prompt:check` 门禁 |
| R5 | Agent 单图替换（原 ReAct 图） | ADR-0009，`feature/pc-config-agent` 已落地 |
| R6 | PC 配置端到端联调 | [pc-config-e2e-2026-11.md](../quality/pc-config-e2e-2026-11.md) |
| R7 | `docs/planning/closure-plan.md` 缺失导致多条断链 | 本文件建立即关闭 |
| R8 | P1-02 快照保留与归档策略 | [deployment-guide.md](../deployment/deployment-guide.md) §6.6：在线 12 个月、单用户 200 条上限、按月归档到 `deploy/backups/`，删除与恢复 SQL 已在库内验证（自引用外键按层处理） |
| R9 | P1-03 前端浏览器视觉验收 | [pc-config-e2e-2026-11.md](../quality/pc-config-e2e-2026-11.md) §8：`frontend/e2e/build-visual.spec.ts` 三条用例覆盖四组界面（八件配置、演示价、无解回退、HITL 表单）+ 截图留档，已入 `e2e:critical` |
| R10 | 消息级反馈闭环（赞/踩 + 原因 + 管理端查看 + 回流评测） | [api-contract.md](../api-contract.md) §5.8；Java `feedback/**` 与 `V25__create_message_feedback.sql`，`MessageFeedbackApiTests`（9 例）、`AdminFeedbackApiTests`（6 例）通过；前端 `frontend/src/features/chat/components/message-feedback.tsx`、管理端 `admin/src/features/feedback/**`；回流脚本 `scripts/feedback/export_eval_cases.py` 只生成 `agent-service/evals/cases-pending/` 草稿，不直接入集 |
| R11 | 输入侧护栏与接口限流 | [services/agent-service/architecture.md](../services/agent-service/architecture.md) §5.1；`agent-service/app/services/input_guard.py`、`rate_limit.py` 接入 `chat.py`（护栏 → 限流 → 幂等）；`tests/test_input_guard.py`（10 例）、`tests/test_rate_limit.py`（9 例）通过；错误码 `input_rejected`（422）与 `rate_limited`（429）已登记在 [api-contract.md](../api-contract.md) §8 |

## 4. 收尾顺序

1. 先做 P0-01 与 P0-02（数据真实性与兼容性完整性），二者都会改变求解输出。
2. 重新运行 Stage 5 三组 Demo 与 §8 指标核对，更新联调报告。
3. 再做 P1-01，扩充候选后复跑指标，确认没有把「无解」改成「超预算」。
4. P1-02 / P1-03 已关闭（见 §3 R8、R9）；剩余收尾执行 §1 的 G-01–G-05。
