# 兼容性 UNKNOWN 按 BLOCKING / ADVISORY 分级

## 背景

当前 [CompatibilityValidator](../../application-service/src/main/java/com/example/agent/pcbuild/application/CompatibilityValidator.java) 对任何缺失字段都返回 `UNKNOWN`，求解器只把 `FAIL` 当作硬冲突。这套语义已经稳定，但有两个后果：

1. `cooler_case_height` 对所有机箱恒为 `UNKNOWN`（机箱缺 `max_cooler_height_mm`），于是**每一套**方案的 `overallStatus` 都是 `UNKNOWN`，`UNKNOWN` 不再携带信息量。
2. 无法区分“CPU 插槽未知”（几乎等于方案不可信）与“散热器限高未知”（可能只是少一条提示）。

Stage 10 要求把关键与辅助的 `UNKNOWN` 分开处理，同时明确“不能把所有 UNKNOWN 一律判 FAIL，也不能自动当 PASS”。

## 决策

1. 每条规则结论新增 `risk_level`，取值 `BLOCKING` 与 `ADVISORY`。
2. `BLOCKING` 用于：硬性物理约束的字段缺失（CPU/主板 `socket`、内存类型、主板板型、显卡长度、散热器高度、供电接口数量）。规则返回 `UNKNOWN` + `BLOCKING` 时：
   - 求解**继续**，不把方案判为无解；
   - 方案**不得**标记为“完全验证通过”，对外必须显示为“待核验”。
3. `ADVISORY` 用于辅助信息缺失（如内存频率、电源效率）。只提示，不影响验证结论。
4. `FAIL` 语义不变：任何 `FAIL` 都不允许进入最终配置。
5. 规则集合或分级变化时递增 `CompatibilityReport.RULE_VERSION`（首次升级为 `pc-compat-2.0.0`）。

## 考虑过的替代方案

- **所有 `UNKNOWN` 都阻断求解**：当前数据下会导致全量无解，产品直接不可用；也违反“不能因数据不完整而生成不了配置”的约束。
- **维持现状（不分级）**：`UNKNOWN` 永远是整体状态，用户无法知道哪一项真正需要核实，也无法解释为什么方案“未完全验证”。
- **把 `UNKNOWN` 直接降级为 `PASS`**：与 [ADR 0015](0015-lifecycle-unknown-is-not-excluded.md) 的“不猜测”原则冲突，会让预算与物理空间结论失去意义。

## 影响

- `CompatibilityCheck` 契约新增 `risk_level`，需要同步 Java DTO、Agent 投影、前端结果卡片与契约文档；`rule_version` 随之升级，历史快照仍保留旧版本与其 `PASS/FAIL/UNKNOWN` 语义。
- “未完全验证”从状态变成状态 + 原因的二元表达，前端需要能区分“有 WARNING 但可用”与“有 BLOCKING UNKNOWN 待核验”。
- 分级本身是判断，不是数据：每条规则属于 `BLOCKING` 还是 `ADVISORY` 必须写在规则定义里并有测试，不允许在调用方临时决定。
