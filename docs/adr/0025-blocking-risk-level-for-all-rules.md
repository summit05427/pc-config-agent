# 八条兼容规则全部为 BLOCKING，接受默认方案显示“待核验”

## 背景

[ADR 0023](0023-compatibility-unknown-risk-levels.md) 引入 `risk_level` 之后，需要决定每条规则归属 `BLOCKING` 还是 `ADVISORY`。

现状是 `cooler_case_height` 对**所有**机箱都返回 `UNKNOWN`：机箱数据里缺 `max_cooler_height_mm`（`docs/pc-config/solver-and-compatibility.md` §5 已记录）。如果它保持 `BLOCKING`，那么每一套方案都会带上“存在必须核实的兼容性缺口”，`overallStatus` 恒为 `UNKNOWN`。

## 决策

1. 八条现有规则全部归为 `BLOCKING`：CPU 插槽、内存类型、主板板型、显卡长度、散热器插槽、散热器限高、显卡供电与电源功率、存储接口。
2. 本阶段新增的唯一规则 `memory_module_count`（内存条数不超过主板插槽数）同样归为 `BLOCKING`。
3. `ADVISORY` 保留枚举值但本期不启用。理由：现有八条都是物理尺寸或供电硬约束，没有一条属于“缺了也不影响装机”的辅助信息。
4. 接受并明确接受后果：在机箱限高数据补齐之前，**每一套方案都会显示为“待核验”**。
5. `CompatibilityReport.RULE_VERSION` 升为 `pc-compat-2.0.0`。

## 考虑过的替代方案

- **把 `cooler_case_height` 降为 `ADVISORY`**：方案会显示为已验证，但掩盖了“散热器可能装不进机箱”这个真实未知；这正好是 [ADR 0015](0015-lifecycle-unknown-is-not-excluded.md) 与 ADR 0023 要防的误导。
- **等机箱限高数据补齐后再分级**：数据补齐属于数据接入工作（见 [ADR 0022](0022-stage10-keeps-runtime-catalog-scope.md)），本阶段不做，等于无限推迟分级。
- **对 `UNKNOWN` 不设风险级别，只保留状态**：无法区分“缺一条提示”与“缺关键物理约束”，也就无法驱动前端展示差异。

## 影响

- 前端结果卡片必须显式渲染“待核验项及缺失字段”，不得把 `UNKNOWN` 渲染成 `PASS`；产品文案不得暗示整机已确认可装。
- 这是产品可见的体验代价：默认方案一律带“待核验”。如果后续业务要求默认展示“已验证”，必须先补齐机箱限高数据并单独评审，不能靠改规则分级来绕过。
- `risk_level` 的归属是规则定义的一部分，必须有测试覆盖；不允许在调用方临时决定某条规则是否阻断。
