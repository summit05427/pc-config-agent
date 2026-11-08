# 治理结论独立为 governance_status，不改写 data_quality_status

## 背景

现有 `Hardware` 只读取 `dataQualityStatus` 字符串，夹具取值为 `VERIFIED_STRUCTURED` / `PARTIAL`，其语义是"结构化字段是否完整、是否有未核验字段"（见 [data-model.md](../pc-config/data-model.md) §3）。Stage 8 需要表达的是治理结论：`VALID` / `INCOMPLETE` / `INVALID` / `CONFLICT`。两者词表不同、判定主体不同、消费者也不同。

## 决策

1. 现有 `data_quality_status` 及其取值、语义、Java 代码与既有文档保持不变，不改夹具、不改注释。
2. 新增独立字段 `governance_status`（`VALID` / `INCOMPLETE` / `INVALID` / `CONFLICT`），只在治理产物与候选池规则中使用。
3. 五个状态字段相互独立，不得互相替代：`data_quality_status`、`governance_status`、`lifecycle_status`、`market_status`、`recommendation_status`。
4. 禁止在生成脚本中把旧值映射成新枚举，也禁止新枚举出现在现有 `catalog.json` 中。

## 考虑过的替代方案

- **迁移到 Stage 8 的四个值**：词表更整洁，但会同时改动现有夹具、Java DTO 注释、两份文档与既有测试断言，且丢失"字段完整度"这一层语义。
- **两套并存并加映射脚本**：会产生"同一事实两个真值"，容易在候选池与在线链路之间出现口径漂移。

## 影响

- 在线链路零改动；Stage 8 的治理结论只能通过新字段表达，消费方必须显式选择字段。
- 文档必须固定五个字段的定义，否则后续很容易把 `governance_status=VALID` 误读成"可以推荐"。
- 若未来要把治理结论接入 Java，只需新增字段读取，不需要迁移旧值。
