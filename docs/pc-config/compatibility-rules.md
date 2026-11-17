# PC 配置兼容性规则

| 项 | 内容 |
| --- | --- |
| 适用范围 | Java `pcbuild` 兼容性判定、`validate` / `validate-partial` / `compose` 的 `checks[]` 语义 |
| 状态 | Current |
| 最后更新 | 2026-11-17 |
| 权威性 | 本文是 9 条兼容规则的唯一详细说明；接口字段与错误码见 [docs/api-contract.md](../api-contract.md) §5.7 |
| 主要证据 | `application-service/.../pcbuild/domain/CompatibilityRule.java`、`application/CompatibilityValidator.java`、`domain/CompatibilityReport.java` |

## 1. 结论先行

- 兼容性由 Java 确定性判定，Agent 与 LLM 只引用结论，不重算、不改写。
- 规则共 **9 条**，全部 `riskLevel=BLOCKING`，`ruleVersion=pc-compat-2.0.0`。
- 字段缺失返回 `UNKNOWN`，不得降级为 `PASS`；只有 `FAIL` 表示硬冲突。
- `validate` 校验完整八类组合；`validate-partial` 只执行「依赖类别全部已选」的规则；`compose` 在落快照前执行完整校验。
- 当前数据下 `cooler_case_height` 常为 `UNKNOWN`：402 款目录中 26 款机箱有 20 款缺 `max_cooler_height_mm`，26 款散热器有 11 款缺 `height_mm`，因此整套方案常汇总为 `UNKNOWN`。

## 2. 九条规则

| `ruleId` | 判定字段 | PASS | FAIL | UNKNOWN |
| --- | --- | --- | --- | --- |
| `cpu_socket_motherboard` | CPU.`socket` / 主板.`socket` | 忽略大小写相等 | 不相等 | 组件缺失或插槽为空 |
| `motherboard_memory_type` | 主板.`memory_type` / 内存.`memory_type` | 忽略大小写相等 | 不相等 | 任一缺失 |
| `motherboard_case_form_factor` | 主板.`form_factor` / 机箱.`supported_mainboard_form_factors` | 列表包含该板型 | 列表不含 | 任一缺失或列表为空 |
| `gpu_case_length` | 显卡.`length_mm` / 机箱.`max_gpu_length_mm` | `<=` 限长 | 超过限长 | 任一为 `null` |
| `cooler_cpu_socket` | CPU.`socket` / 散热.`supported_sockets` | 列表包含该插槽 | 不含 | 插槽或列表缺失 |
| `cooler_case_height` | 散热.`height_mm` / 机箱.`max_cooler_height_mm` | `<=` 限高 | 超过限高 | 任一为 `null` |
| `gpu_psu_power` | CPU/GPU `tdp_w`、GPU `external_power`、PSU `wattage_w` 与接口数 | 见 §3 | 见 §3 | 任一功率、外接供电或接口数量缺失 |
| `storage_motherboard_m2` | 存储.`interface` / `form_factor`、主板.`m2_slot_count` / `sata_ports` | M.2 且有 M.2 槽，或 SATA 且有 SATA 口 | 对应接口数为 0 | 接口无法识别或数量缺失 |
| `memory_module_count` | 内存.`module_count` / 主板.`memory_slots` | 条数 `<=` 插槽数 | 条数 `>` 插槽数 | 任一缺失 |

规则的声明顺序就是判定顺序，`checks[]` 按此顺序返回。

## 3. `gpu_psu_power` 细节

1. 先校验供电接口：显卡需要的 8pin / 12VHPWR 数量大于电源提供数量即 `FAIL`。
2. 再计算基础负载：`150W + cpu.tdp_w + gpu.tdp_w`。
3. 电源额定功率低于基础负载为 `FAIL`；低于 `基础负载 × 1.3`（按 `×13/10` 取整）为 `WARNING`；否则 `PASS`。

`WARNING` 只由这条规则产生，表示可用但没有 30% 冗余，不阻止生成方案。

## 4. 状态汇总与风险级别

- 汇总取最严重状态，优先级 `FAIL > UNKNOWN > WARNING > PASS`；空 `checks[]` 视为 `UNKNOWN`。
- `UNKNOWN` 是一等状态：调用方必须展示为「未验证」，不能当作通过。
- `BLOCKING` 表示「该字段缺失时方案不得标记为完全验证通过」，**不是**阻断生成；当前 9 条规则全部为 `BLOCKING`。
- `validate` 的 `valid` 只看是否存在 `FAIL`；`UNKNOWN` 不影响 `valid`，但影响展示口径。
- `validate-partial` 不返回未执行规则；没有任何规则可执行时 `overallStatus=UNKNOWN`，并回填 `missingFields`（形如 `cpu.socket`）。

## 5. 调用方职责

| 调用方 | 职责 |
| --- | --- |
| Agent `build_architect` | 用 `check_partial_compatibility` 提前发现核心冲突；用 `compose_pc_build` 触发完整校验；只按 `FAIL` 修正，不把 `UNKNOWN` 说成通过 |
| Agent `response_generator` | 原文引用 `overall_status` 与逐条 `message`；`UNKNOWN` / `WARNING` 必须显式说明 |
| 前端 `BuildResultCard` | `UNKNOWN` 使用弱化样式并标注「待核验」，不得使用成功色 |
| 数据维护 | 补齐机箱限高、散热高度等字段以降低 `UNKNOWN` 比例 |

## 6. 相关文档

- 接口字段：[docs/api-contract.md](../api-contract.md) §5.7
- Agent 工作流：[agent-workflows.md](../services/agent-service/agent-workflows.md)
- 数据现状与字段缺失：[data.md](./data.md)
- 术语：[glossary.md](./glossary.md)
