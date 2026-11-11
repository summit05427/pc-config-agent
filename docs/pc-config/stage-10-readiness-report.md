# Stage 10 就绪度报告（求解器与兼容性引擎）

| 项 | 内容 |
| --- | --- |
| 状态 | 已实施首批改造（2026-11-09） |
| 权威性 | 本文件记录 Stage 10 的当前能力、数据边界与验收口径；规则与公式细节见 [solver-and-compatibility.md](./solver-and-compatibility.md)，测试事实见 [testing-and-evaluation.md](./testing-and-evaluation.md) |
| 关联决策 | [ADR 0022](../adr/0022-stage10-keeps-runtime-catalog-scope.md)、[0023](../adr/0023-compatibility-unknown-risk-levels.md)、[0024](../adr/0024-scoring-version-in-snapshot-json.md)、[0025](../adr/0025-blocking-risk-level-for-all-rules.md) |

## 1. 审计结论：原计划的一半是“已实现”

Stage 10 的任务书按“从基础做起”描述兼容性与求解，实际审计（逐条对照源码）显示以下能力在本轮改造**之前**就已存在：

| 能力 | 证据 |
| --- | --- |
| 八条兼容规则、`UNKNOWN` 一等状态、仅 `FAIL` 阻断 | `pcbuild/application/CompatibilityValidator.java`、`domain/CompatibilityRule.java` |
| 固定顺序 DFS、增量剪枝、预算剪枝、无预算探针 | `pcbuild/application/BuildSolver.java` |
| 整数评分 + 性价比分支 + 场景权重 | `BuildScenario.java` |
| `solver_version`、`rule_version`、快照落库与越权保护 | `BuildSolverVersion.java`、`CompatibilityReport.java`、`V24__create_pc_build_snapshots.sql` |
| 五个测试类（pcbuild 51 例） | `application-service/src/test/java/com/example/agent/pcbuild/` |

因此本阶段只做增量，不重写已有稳定模块。

## 2. 数据边界（决定验收上限）

| 数据 | 运行时规模 | 主数据 | 结论 |
| --- | --- | --- | --- |
| 硬件目录 | **234 条**（CPU 29 / GPU 11 / 主板 65 / 内存 16 / 存储 6 / 散热 66 / 机箱 5 / 电源 36） | `data/pc-config/master/hardware-master.jsonl` 8,238 条 | 目录已由数据侧扩充，主数据仍未整体接入 |
| 跑分 | **12 条** | 3,557 条，含 `SINGLE_THREAD` / `DISK_MARK` | 无推理与编码类指标；单线程分已随 CPU 条目提供 |
| 报价 | **214 条**，仍含演示价 | Stage 9 采集中 | 不得宣称“真实市场已验证” |

> 2026-11-09 更正：本节原写“28 条”，是数据侧扩充前的口径。目录扩到数百条后暴露了一个真实缺陷——候选池“先截断后剪枝”会取到与主板内存类型/CPU 插槽不匹配的前 N 条，导致所有组合 `FAIL`、求解无解。已改为“先按上游池过滤再截断”，详见 [质量报告 §6](../quality/pc-config-stage-10-report.md)。

缺失字段（决定了哪些规则只能返回 `UNKNOWN`）：芯片组支持列表、BIOS 版本、VRM、主板最大内存容量、QVL、M.2 通道共享、GPU 厚度、电源峰值与分路。

## 3. 本轮实际改动

1. 新增 `WorkloadProfile`（六值）与 `RenderMode`，旧场景值保留并归一化；`GENERAL` 与原 `BALANCED` 结果完全一致。
2. `RiskLevel`（`BLOCKING` / `ADVISORY`）进入每条兼容结论；九条规则全部 `BLOCKING`。
3. 新增第九条规则 `memory_module_count`（内存条数 ≤ 主板插槽数），进入增量剪枝。
4. 候选排序按用途分派（`BALANCED` / `SINGLE_THREAD_FIRST` / `MULTICORE_FIRST` / `VRAM_FIRST` / `GPU_SCORE_FIRST`），全部以 `hardwareId` 兜底保证确定性。
5. 评分新增游戏单线程混合（`SINGLE_THREAD_SCALE=10` 仅量纲对齐）与显存加成（AI 3000 / 视频 1000 分每 GB，上限 24GB）。
6. `scoring_version`（`pc-scoring-1.0.0`）与 `workloadProfile`、`renderMode` 写入 `requirements_snapshot` JSON，未新增数据库列。
7. 版本升级：`pc-solver-2.0.0` → `pc-solver-2.1.0`、`pc-compat-2.0.0`、`pc-scoring-1.0.0`。
8. 兼容感知池构建：主板按 CPU 池插槽、内存按主板池内存类型、散热按 CPU 池扣具先过滤再截断（修复目录扩充后的“必然无解”缺陷）。
9. `preference`（`PERFORMANCE` / `VALUE`）：有预算且为 `VALUE` 时按性价比排序，否则按性能总分。
10. 逐件解释：`componentReasons` 给出每类硬件的得分贡献、价格占比与候选排序依据，全部由 Data 推导，禁止 LLM 生成。

## 4. 明确不做（有依据）

芯片组支持、BIOS、VRM、QVL、M.2 通道共享、GPU 厚度、电源峰值与分路、真实推理/编码基准、快照新增列、扩运行时候选、独立配置页、OR-Tools。前七项因主数据无字段；后五项因无证据或与现有实现重复。

## 5. 验收口径

- **已通过**：Java 51 个测试类 403 例全绿；Agent 544 例、覆盖 92.5%+；前端 497 例、行覆盖 92.8%；lint / type-check / mypy / ruff 全通过。
- **未通过、也不得声称通过**：真实数据 E2E。报价仍含演示价，Stage 9 首批真实报价导入前，“真实市场配置已验证”不成立。
- **已采集**：求解耗时与组合规模基线（`BuildSolverBenchmarkTests`），数字见 [质量报告 §5](../quality/pc-config-stage-10-report.md)。结论是兼容感知池构建带来 3.6 倍搜索成本，换取真实数据下“有解”，不宣称优化提升。
- **产品可见代价**：九条规则全 `BLOCKING` 且机箱缺限高，默认方案一律显示“待核验”，见 ADR 0025。

## 6. 下一步

1. 数据接入独立立项：主数据 → 运行时目录、跑分覆盖、真实报价覆盖（前置：Stage 9 首批 Offer）。
2. 数据补齐后回填机箱 `max_cooler_height_mm`、主板 `max_memory_gb` 与 `m2_slot_count`，把两条恒 `UNKNOWN` 的规则变为可判定。
3. 采集求解性能基线，再决定是否需要 OR-Tools；当前无证据支持引入。
