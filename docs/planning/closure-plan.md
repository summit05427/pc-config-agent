# 收尾计划：当前待办与放行条件

| 项 | 内容 |
| --- | --- |
| 状态 | Current |
| 最后核验 | 2026-11-08 |
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
| P1-02 | 中 | 定义快照保留与归档策略（本期 append-only、只增不删） | Java 快照表、运维 | 给出保留周期、归档方式与回滚方案 |
| P1-03 | 中 | 前端浏览器人工视觉验收（八件配置、演示价提示、无解回退） | `frontend/` | 三组 Demo 输入在 5273 页面复现并留档 |
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

## 4. 收尾顺序

1. 先做 P0-01 与 P0-02（数据真实性与兼容性完整性），二者都会改变求解输出。
2. 重新运行 Stage 5 三组 Demo 与 §8 指标核对，更新联调报告。
3. 再做 P1-01，扩充候选后复跑指标，确认没有把「无解」改成「超预算」。
4. 最后做 P1-02 / P1-03，并执行 §1 的 G-01–G-05。
