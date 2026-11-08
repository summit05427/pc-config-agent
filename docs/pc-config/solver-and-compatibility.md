# PC 配置求解与兼容性

| 项 | 内容 |
| --- | --- |
| 状态 | 已验证（逐条对照 2026-11-08 源码） |
| 最后核验 | 2026-11-08 |
| 权威性 | 本文件描述候选过滤、搜索剪枝、评分公式与八条兼容规则；接口字段以 [api-contract.md](../api-contract.md) §5.7 为准，术语见 [glossary.md](./glossary.md) |
| 主要证据 | `pcbuild/application/BuildSolver.java`、`CompatibilityValidator.java`、`BuildSolveService.java`、`domain/CompatibilityRule.java`、`BuildScenario.java` |

## 1. 输入与候选过滤

`BuildSolver.solve` 接收需求、硬件全集、报价全集、跑分全集、`catalogVersion`、`offerDataStatus` 与询价日期（`LocalDate.now()`）。候选按以下条件过滤：

- 硬件 `isSolverEligible()`：`recommendation_status=ELIGIBLE` 且生命周期不是 `DISCONTINUED` / `EOL`。
- 需求给出 `minMemoryGb` / `minStorageGb` 时，对应容量必须非空且不小于下限；容量缺失即淘汰。
- 必须存在 `isUsableOn(pricingDate)` 的报价；`requireVerifiedOffers=true` 时只接受 `OWNER_VERIFIED`。
- 跑分不是准入条件；缺失时按 0 分参与排序与评分。

排序与上限：CPU / GPU 按跑分降序、价格升序、`hardware_id` 升序，各取前 12；其他类别按价格升序、`hardware_id` 升序，各取前 8。任一类别候选为空即返回 `NO_CANDIDATES`，并带上缺失类别与各类候选数。

## 2. 搜索与剪枝

固定枚举顺序为 `CPU → MOTHERBOARD → MEMORY → GPU → PSU → CASE → COOLER → STORAGE`，使用深度优先搜索：

- 增量剪枝：加入主板查 `cpu_socket_motherboard`，内存查 `motherboard_memory_type`，电源查 `gpu_psu_power`，机箱查板型与显卡长度，散热查插槽与限高，存储查 M.2 / SATA；只把 `FAIL` 当作冲突。
- 预算剪枝：报价均为正，累计总价只会增加，因此 `nextPrice > budgetMaxFen` 可安全剪掉整棵子树。
- 完整组合仍会跑一次全量八条校验；`hasFailure()` 为真则丢弃。只有通过校验的完整组合才计入 `evaluatedCombinationCount` 并更新最低可行价。
- 若预算内没有最优方案，会用无预算的探针搜索再跑一轮，只求最低可行总价，不会把探针命中的超预算方案当结果返回。

## 3. 评分公式

评分全程使用整数运算，金额不参与浮点计算：

```text
cpuScore   = max(0, round(cpuBenchmark.score))
gpuScore   = max(0, round(gpuBenchmark.score))
weighted   = (cpuScore * cpuWeight + gpuScore * gpuWeight) / 100   // 整数除法
memoryBonus  = min(max(memory.capacity_gb, 0), 64) * 500
storageBonus = min(max(storage.capacity_gb, 0), 2048) * 20
score = weighted + memoryBonus + storageBonus
```

| 场景 | CPU 权重 | GPU 权重 |
| --- | --- | --- |
| `GAMING` | 30 | 70 |
| `CREATIVE` | 55 | 45 |
| `PROGRAMMING` | 80 | 20 |
| `WORKSTATION` | 60 | 40 |
| `OFFICE` | 85 | 15 |
| `BALANCED` | 50 | 50 |

`VIDEO_EDITING` 归一化为 `CREATIVE`，`GENERAL_USE` 归一化为 `BALANCED`；其他未知值解析为 `null`，由请求校验拒绝。

最优方案选择：有预算时按 `score` 降序 → 总价升序 → 组合标识升序；无预算时先按性价比 `score * 1_000_000 / price`（`price<=0` 记 0）降序 → `score` 降序 → 总价升序 → 标识升序。内存频率、CL、电源效率等不进入评分。

## 4. 八条兼容规则

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

`gpu_psu_power` 顺序：先校验供电接口，显卡需要数量大于电源提供数量即 `FAIL`；再算基础负载 `150 + cpuTdp + gpuTdp`。电源额定功率低于基础负载为 `FAIL`；低于 `基础负载 × 1.3`（按 `×13/10` 取整）为 `WARNING`；否则 `PASS`。

## 5. WARNING 与 UNKNOWN 的处理

- `WARNING` 只由 `gpu_psu_power` 产生，表示可用但无 30% 冗余；不是硬冲突，求解继续。
- `UNKNOWN` 是一等状态：字段缺失必须返回它，不能跳过规则，也不能展示为 `PASS`。
- 报告汇总取最严重状态，优先级 `FAIL > UNKNOWN > WARNING > PASS`；当前 `cooler_case_height=UNKNOWN` 会让整套方案 `overallStatus=UNKNOWN`。
- 求解器只以 `FAIL` 判定冲突；`WARNING` 与 `UNKNOWN` 都不阻止生成方案。

## 6. `solved=false` 的 Failure 语义

| `reason` | 触发条件 | `minimumRequiredBudgetFen` |
| --- | --- | --- |
| `NO_CANDIDATES` | 至少一个类别没有可用候选 | `null`；`missingCategories` 与 `candidateCounts` 有值 |
| `NO_COMPATIBLE_BUILD` | 候选存在，但没有组合通过八条规则 | `null` |
| `BUDGET_EXCEEDED` | 存在兼容组合，但全部超出预算 | 探针搜索得到的最低可行总价（分） |

Failure 还包含 `message`、`candidateCounts`、`evaluatedCombinationCount`。`evaluatedCombinationCount` 只统计通过兼容校验的完整组合。若探针也没有可行组合，`minimumRequiredBudgetFen` 无值，结果归为 `NO_COMPATIBLE_BUILD`。

无解时求解器绝不修改需求：不放宽预算、不删除类别、不接受硬冲突。Agent 侧允许在校验失败后重解一次，且只放宽 `require_verified_offers`，预算与兼容性约束不变，见 [agent-workflow.md](./agent-workflow.md) §3。

## 7. 快照写入时机

`BuildSolveService.solve` 带事务：求解成功后才生成新的 `build_id` 与 `created_at` 并写入 `pc_build_snapshots`；求解失败直接返回 Failure，不落库。快照同时记录 `solver_version`（`pc-solver-1.0.0`）、`compatibility_rule_version`（`pc-compat-1.0.0`）与 `catalog_version`，用于判断历史结果是否可比。读取时同时按 `build_id` 与 `user_id` 查询，越权或不存在均返回 `40302`。
