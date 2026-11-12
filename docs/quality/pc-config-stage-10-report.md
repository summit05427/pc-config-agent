# PC 配置 Stage 10 质量报告

日期：2026-11-09 · 分支：`feature/pc-config-data-governance` · 求解器版本 `pc-solver-2.1.0` · 兼容规则版本 `pc-compat-2.0.0` · 评分策略版本 `pc-scoring-1.0.0`

## 1. 结论

Stage 10 的**契约、规则体系、用途画像、求解改造**已完成并全绿；**性能量化**已补基线；**真实数据 E2E、数据缺口规则、需求提取广度**未完成，原因均为数据侧缺失，不是代码遗留。

一句话：可交付的增量已交付；Stage 10 原文中依赖“规格字段可用”的部分，在数据补齐前无法真实达成，不得声称达成。

## 2. 完成情况

| Stage 10 章节 | 状态 | 说明 |
| --- | --- | --- |
| 10.0 代码与数据审计 | 完成 | 见 [roadmap](../planning/roadmap.md) §6 |
| 10.1 兼容性规则 | 部分 | 新增 `memory_module_count`；九条规则统一 `risk_level`；芯片组/BIOS/VRM/QVL/M.2 通道共享因无字段无法实现 |
| 10.2 用途画像 | 部分 | 六个 `WorkloadProfile` + 渲染取向 + 澄清流程；分辨率、刷新率、视频工作流等需求提取未做 |
| 10.3 求解算法 | 完成 | 用途感知候选排序、兼容感知池构建、`preference` 性价比分支、确定性 tie-break |
| 10.4 解释与快照 | 完成 | 逐件理由 `componentReasons` + `reasonSummary`；快照含画像/渲染取向/评分版本，无新增迁移 |
| 10.5 契约联调 | 完成 | Java DTO、Agent 投影、前端类型与卡片、`docs/` 契约文档四处同步 |
| 9.4 性能基线 | 完成 | 见 §5 |
| 9.5 真实数据 E2E | **未完成** | 报价仍含演示价；不得声称“真实市场配置已验证” |

## 3. 契约变更

1. `SolveRequest` 新增 `scenario` 新取值（`RENDERING`、`AI_INFERENCE` 等）与 `renderMode`（`CPU`/`GPU`）。
2. `SolveRequest` 新增可空 `preference`（`PERFORMANCE`/`VALUE`）：有预算且为 `VALUE` 时按性价比排序，否则按性能总分。
3. `BuildResultResponse` 新增 `componentReasons`（逐件理由）与 `reasonSummary`。
4. `CompatibilityCheckResponse` 新增 `riskLevel`（当前九条规则全部 `BLOCKING`）。
5. `RequirementsResponse` 新增 `workloadProfile`、`renderMode`、`scoringVersion`。

Agent 侧同名字段以 snake_case 透传；前端对非法值只丢弃该字段，不整块失败。

## 4. 测试结果（本地实测）

| 面 | 命令 | 结果 |
| --- | --- | --- |
| Java | `.\mvnw.cmd verify` | 403 例，0 失败 / 0 错误 / 0 跳过；51 个测试类 |
| Agent | `ruff` / `mypy` / `pytest` | 全通过；544 例；覆盖 92.5%+ |
| 前端 | `lint:ci` / `type-check` / `test:coverage` | 0 warning；497 例；行覆盖 92.8% |

新增覆盖点：`preference` 排序分支、逐件理由文本约束（禁止 `FPS`/`tok/s` 等无依据表述）、内存条数边界、用途排序策略、理由在缺失/损坏时的降级、`component_reasons` 透传。

## 5. 求解性能基线

测量环境：OpenJDK 21.0.12.1 LTS、Maven 3.10.0、i5-11400H；测量时机器同时运行 postgres、pgvector、redis、litellm、prometheus。每场景 10 次 warmup + 20 次测量，取中位数与 nearest-rank P95。

| 场景 | 版本 | 候选数（CPU/MB/MEM/GPU/PSU/CASE/COOLER/STORAGE） | 评估组合数 | 中位 | P95 |
| --- | --- | --- | --- | --- | --- |
| C 合成 200/类 | 1.0.0 | 12/8/8/12/8/8/8/8 | 18,432 | 134 ms | 192 ms |
| C 合成 200/类 | 2.1.0 | 12/8/8/12/8/8/8/8 | 113,068 | 481 ms | 517 ms |
| D 合成 200/类 `AI_INFERENCE` | 2.1.0 | 同 C | 145,818 | 493 ms | 540 ms |
| A 运行时目录 `GAMING` 15000 元 | 2.1.0 | 12/8/4/5/8/5/8/6 | 486,960 | 1,211 ms | 1,402 ms |
| B 运行时目录 无预算 | 2.1.0 | 同 A | 921,600 | 2,298 ms | 2,481 ms |

说明：

- A/B 与 1.0.0 不可直接对照：测量时运行时目录已从 28 条增至 225 条（现为 234 条），数据量本身就是变量。
- C 的差异来自**兼容感知池构建**：先按 CPU 插槽、主板内存类型、CPU 散热扣具过滤再截断，候选池保持满额，DFS 需要探索更多组合。
- 该代价是必要的，见 §6。**不存在**“优化后更快”的结论，不得这么写。

## 6. 数据扩充暴露的真实缺陷

现象：内存池按价格取前 8 全为 DDR4（22,800 分），而 65 块主板全为 DDR5，`MOTHERBOARD_MEMORY_TYPE` 对所有组合 `FAIL`，求解返回无解。

根因：候选池构建是「先截断后剪枝」，在数十条级别的演示目录上成立；目录扩到数百条后，价格最低的前 N 条与其它类别不兼容的概率极高，导致正确解被截断掉。

修复：改为「先按已截断的上游池过滤，再截断」——主板按 CPU 池插槽过滤、内存按主板池内存类型过滤、散热按 CPU 池扣具过滤，各池仍保持 12/8 上限与 `hardwareId` 兜底。回退该修复会让真实数据下的求解回到“必然无解”。

## 7. 剩余缺口

1. **真实数据 E2E**：2026-11-11 实测 3,837 条报价中仍有 18 条演示价、2,474 条 `FALLBACK` 价格与 3,809 条可得性 `UNKNOWN`，`requireVerifiedOffers` 之外的生产链路不能宣称“已核验”。
2. **规格字段**：芯片组支持列表、BIOS 版本、VRM、QVL、M.2 通道共享、GPU 厚度、机箱限高缺失，相关规则只能 `UNKNOWN`。
3. **需求提取广度**：只提取用途、渲染取向、偏好；分辨率/刷新率、视频工作流、开发工具未做。
4. **文档债务**：已于 2026-11-11 文档治理中处理：`demo-scope.md`、`candidate-shortlist.md` 等过期文档删除，`pc-config/README.md` 与 `data.md` 改为实测口径；当前目录 3,974 款、报价 3,837 条，见 [roadmap](../planning/roadmap.md) §2。

## 8. 可量化的边界声明

- 逐件理由只陈述得分贡献、价格占比、候选排序依据，不含 FPS、渲染时长、token/s 等未经 Benchmark 支撑的承诺。
- `G3D_MARK` 只作图形能力代理，不等同于游戏帧率；`AI_INFERENCE` 只用显存容量与图形分做排序依据，不承诺任何模型可运行。
- 九条规则全部 `BLOCKING`，因此默认方案会显示“待核验”；这是刻意选择，避免把 `UNKNOWN` 说成 `PASS`。
