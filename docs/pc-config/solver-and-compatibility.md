# PC 配置求解与兼容性

| 项 | 内容 |
| --- | --- |
| 状态 | 已验证（逐条对照 2026-11-09 源码） |
| 最后核验 | 2026-11-09 |
| 权威性 | 本文件描述候选过滤、搜索剪枝、评分公式、用途画像与九条兼容规则；接口字段以 [api-contract.md](../api-contract.md) §5.7 为准，术语见 [glossary.md](./glossary.md) |
| 主要证据 | `pcbuild/application/BuildSolver.java`、`CompatibilityValidator.java`、`domain/CompatibilityRule.java`、`WorkloadProfile.java`、`BuildScenario.java`、`ScoringPolicyVersion.java` |

## 1. 输入与候选过滤

`BuildSolver.solve` 接收需求、硬件全集、报价全集、跑分全集、`catalogVersion`、`offerDataStatus` 与询价日期（`LocalDate.now()`）。候选按以下条件过滤：

- 硬件 `isSolverEligible()`：`recommendation_status=ELIGIBLE` 且生命周期不是 `DISCONTINUED` / `EOL`。
- 需求给出 `minMemoryGb` / `minStorageGb` 时，对应容量必须非空且不小于下限；容量缺失即淘汰。
- 必须存在 `isUsableOn(pricingDate)` 的报价；`requireVerifiedOffers=true` 时只接受 `OWNER_VERIFIED`。
- 跑分不是准入条件；缺失时按 0 分参与排序与评分。

排序与上限：各取前 12（CPU / GPU）、前 8（其他类别）；所有排序均以 `hardware_id` 升序兜底，保证确定性。排序键由 `WorkloadProfile` 的候选排序策略决定：

| 排序策略 | 适用用途 | CPU | GPU | 存储 |
| --- | --- | --- | --- | --- |
| `BALANCED` | `GENERAL`、`RENDERING` | 跑分降序 | 跑分降序 | 价格升序 |
| `SINGLE_THREAD_FIRST` | `GAMING` | 单线程分降序 → 跑分降序 | 跑分降序 | 价格升序 |
| `MULTICORE_FIRST` | `PROGRAMMING` | 核心数降序 → 跑分降序 | 跑分降序 | 价格升序 |
| `VRAM_FIRST` | `AI_INFERENCE` | 跑分降序 | 显存降序 → 跑分降序 | 价格升序 |
| `GPU_SCORE_FIRST` | `VIDEO_EDITING` | 跑分降序 | 跑分降序 | 容量降序 → 价格升序 |

除表中列出的类别外，其余类别一律按价格升序、`hardware_id` 升序。任一类别候选为空即返回 `NO_CANDIDATES`，并带上缺失类别与各类候选数。

池构建必须**先过滤再截断**：主板只保留命中「已截断 CPU 池插槽集合」的候选，内存只保留命中「已截断主板池内存类型集合」的候选，散热只保留支持 CPU 池任一插槽扣具的候选，之后才按上表排序并截断到 12/8。原因是运行时目录已扩到数百条，按价格取前 N 会把与主板内存类型或 CPU 插槽不匹配的候选选进池，导致所有组合 `FAIL`、求解直接无解。

选优偏好：`preference=VALUE` 且存在预算时，按 `score * 1_000_000 / price` 降序排序；`PERFORMANCE` 或未提供时按总分降序。偏好只影响“同样合法的方案里挑哪个”，不会放宽预算或兼容性约束。

## 2. 搜索与剪枝

固定枚举顺序为 `CPU → MOTHERBOARD → MEMORY → GPU → PSU → CASE → COOLER → STORAGE`，使用深度优先搜索：

- 增量剪枝：加入主板查 `cpu_socket_motherboard`，内存查 `motherboard_memory_type` 与 `memory_module_count`，电源查 `gpu_psu_power`，机箱查板型与显卡长度，散热查插槽与限高，存储查 M.2 / SATA；只把 `FAIL` 当作冲突。
- 预算剪枝：报价均为正，累计总价只会增加，因此 `nextPrice > budgetMaxFen` 可安全剪掉整棵子树。
- 完整组合仍会跑一次全量九条校验；`hasFailure()` 为真则丢弃。只有通过校验的完整组合才计入 `evaluatedCombinationCount` 并更新最低可行价。
- 若预算内没有最优方案，会用无预算的探针搜索再跑一轮，只求最低可行总价，不会把探针命中的超预算方案当结果返回。

## 3. 评分公式

评分全程使用整数运算，金额不参与浮点计算：

```text
cpuScore   = max(0, round(cpuBenchmark.score))                      // 非 GAMING
cpuScore   = (cpuScore * 50 + max(0, round(cpuBenchmark.secondaryScore)) * 10 * 50) / 100   // GAMING
gpuScore   = max(0, round(gpuBenchmark.score))
weighted   = (cpuScore * cpuWeight + gpuScore * gpuWeight) / 100   // 整数除法
memoryBonus  = min(max(memory.capacity_gb, 0), 64) * 500
storageBonus = min(max(storage.capacity_gb, 0), 2048) * 20
vramBonus    = min(max(gpu.vram_gb, 0), 24) * (3000 if AI_INFERENCE else 1000 if VIDEO_EDITING else 0)
score = weighted + memoryBonus + storageBonus + vramBonus
```

`SINGLE_THREAD_SCALE = 10` 只做量纲对齐：PassMark 单线程分与 CPUMARK 分数量级相差约 10 倍，乘 10 不引入额外权重语义。`GAMING` 的 `cpuScore` 取两者等权混合，其余用途仍只用 `CPUMARK`。

| 用途画像 `WorkloadProfile` | 归一化场景 | CPU 权重 | GPU 权重 | 额外加成 |
| --- | --- | --- | --- | --- |
| `GENERAL` | `BALANCED` | 50 | 50 | 无 |
| `GAMING` | `GAMING` | 30 | 70 | 单线程混合 |
| `VIDEO_EDITING` | `CREATIVE` | 55 | 45 | 显存 × 10 分/GB |
| `PROGRAMMING` | `PROGRAMMING` | 80 | 20 | 无 |
| `RENDERING` | `PROGRAMMING`（`renderMode=CPU`）/ `GAMING`（`GPU`）/ `CREATIVE`（未指定） | 见左 | 见左 | 无 |
| `AI_INFERENCE` | `AI_INFERENCE` | 40 | 60 | 显存 × 3000 分/GB |

旧值仍可作为输入并被归一化：`CREATIVE → VIDEO_EDITING`、`BALANCED`/`OFFICE → GENERAL`、`WORKSTATION → RENDERING`。`GENERAL` 与改造前的 `BALANCED` 在排序与评分上完全一致，历史结果可直接对照。

显存加成与单线程混合只影响评分相对次序，不代表推理速度或游戏帧率；项目没有对应的真实 Benchmark，结果中不得据此承诺 tok/s 或 FPS。

最优方案选择：有预算时按 `score` 降序 → 总价升序 → 组合标识升序；无预算时先按性价比 `score * 1_000_000 / price`（`price<=0` 记 0）降序 → `score` 降序 → 总价升序 → 标识升序。内存频率、CL、电源效率等不进入评分。

## 4. 九条兼容规则

九条规则的 `risk_level` 全部为 `BLOCKING`：它们都是物理尺寸或供电硬约束，没有“缺了也不影响装机”的辅助信息。`BLOCKING` 的含义见 §5，不代表会把 `UNKNOWN` 变成 `FAIL`。

| `ruleId`（判定字段） | PASS | FAIL | UNKNOWN |
| --- | --- | --- | --- |
| `cpu_socket_motherboard`（CPU.socket / 主板.socket） | 忽略大小写相等 | 不相等 | 组件缺失或 socket 为空 |
| `motherboard_memory_type`（主板.memory_type / 内存.memory_type） | 忽略大小写相等 | 不相等 | 任一缺失 |
| `motherboard_case_form_factor`（主板.form_factor / 机箱.supported_mainboard_form_factors） | 列表包含该板型 | 列表不含 | 任一缺失或列表为空 |
| `gpu_case_length`（显卡.length_mm / 机箱.max_gpu_length_mm） | `<=` 限长 | 超过限长 | 任一为 `null` |
| `cooler_cpu_socket`（CPU.socket / 散热.supported_sockets） | 列表包含该插槽 | 不含 | 插槽或列表缺失 |
| `cooler_case_height`（散热.height_mm / 机箱.max_cooler_height_mm） | `<=` 限高 | 超过限高 | 任一为 `null`；当前机箱均缺限高，故恒为 `UNKNOWN` |
| `gpu_psu_power`（CPU.tdp_w、GPU.tdp_w、GPU.external_power、PSU.wattage_w 与接口数） | 见下方说明 | 见下方说明 | 任一功率、外接供电或接口数量缺失 |
| `storage_motherboard_m2`（存储.interface / form_factor、主板.m2_slot_count / sata_ports） | M.2 且有 M.2 槽，或 SATA 且有 SATA 口 | 对应接口数为 0 | 接口无法识别或数量缺失 |
| `memory_module_count`（内存.module_count / 主板.memory_slots） | 条数 `<=` 插槽数 | 条数 `>` 插槽数 | 任一缺失 |

`gpu_psu_power` 顺序：先校验供电接口，显卡需要数量大于电源提供数量即 `FAIL`；再算基础负载 `150 + cpuTdp + gpuTdp`。电源额定功率低于基础负载为 `FAIL`；低于 `基础负载 × 1.3`（按 `×13/10` 取整）为 `WARNING`；否则 `PASS`。

## 5. WARNING、UNKNOWN 与风险级别

- `WARNING` 只由 `gpu_psu_power` 产生，表示可用但无 30% 冗余；不是硬冲突，求解继续。
- `UNKNOWN` 是一等状态：字段缺失必须返回它，不能跳过规则，也不能展示为 `PASS`。
- 报告汇总取最严重状态，优先级 `FAIL > UNKNOWN > WARNING > PASS`；当前 `cooler_case_height=UNKNOWN` 会让整套方案 `overallStatus=UNKNOWN`。
- 求解器只以 `FAIL` 判定冲突；`WARNING` 与 `UNKNOWN` 都不阻止生成方案。
- 每条结论携带 `risk_level`（`BLOCKING` / `ADVISORY`）。`BLOCKING` 表示“该字段缺失时方案不得标记为完全验证通过”，**不是**阻断求解；`ADVISORY` 只提示。当前九条规则全部为 `BLOCKING`，因此默认方案一律展示为“待核验”，直到机箱限高等数据补齐，见 [PC 配置模块决策合并记录](../adr/0027-pc-config-decisions.md) §4.4。

## 6. `solved=false` 的 Failure 语义

| `reason` | 触发条件 | `minimumRequiredBudgetFen` |
| --- | --- | --- |
| `NO_CANDIDATES` | 至少一个类别没有可用候选 | `null`；`missingCategories` 与 `candidateCounts` 有值 |
| `NO_COMPATIBLE_BUILD` | 候选存在，但没有组合通过九条规则 | `null` |
| `BUDGET_EXCEEDED` | 存在兼容组合，但全部超出预算 | 探针搜索得到的最低可行总价（分） |

Failure 还包含 `message`、`candidateCounts`、`evaluatedCombinationCount`。`evaluatedCombinationCount` 只统计通过兼容校验的完整组合。若探针也没有可行组合，`minimumRequiredBudgetFen` 无值，结果归为 `NO_COMPATIBLE_BUILD`。

无解时求解器绝不修改需求：不放宽预算、不删除类别、不接受硬冲突。Agent 侧允许在校验失败后重解一次，且只放宽 `require_verified_offers`，预算与兼容性约束不变，见 [agent.md](./agent.md) §3。

## 7. 快照写入时机

`BuildSolveService.solve` 带事务：求解成功后才生成新的 `build_id` 与 `created_at` 并写入 `pc_build_snapshots`；求解失败直接返回 Failure，不落库。快照同时记录 `solver_version`（`pc-solver-2.1.0`）、`compatibility_rule_version`（`pc-compat-2.0.0`）与 `catalog_version`，用于判断历史结果是否可比。`workload_profile`、`render_mode` 与 `scoring_version`（`pc-scoring-1.0.0`）写入 `requirements_snapshot` JSON，不新增表列，见 [PC 配置模块决策合并记录](../adr/0027-pc-config-decisions.md) §4.2。读取时同时按 `build_id` 与 `user_id` 查询，越权或不存在均返回 `40302`。
