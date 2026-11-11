# 报价来源三值分离，页面观测价不得进入生产求解

## 背景

现有 `price_source` 只有两个取值：`OWNER_VERIFIED`（人工核验）与 `MOCK_DEMO`（演示）。Stage 9 要接入淘宝页面采集得到的真实报价，如果直接写成 `OWNER_VERIFIED`，「程序看到的」与「人确认过的」会被混为一谈，`verifiedCount` 也随之失去意义。

同时，现有 `Offer.isUsableOn()` 把 `MOCK` 视为可用，`cheapestUsableByHardware(requireVerified=false)` 会选到演示价，`build_solver` 重试时还会强制降级为不要求核验——这些路径会让未核验价格进入推荐结果。

## 决策

1. `price_source` 扩展为三值：`OWNER_VERIFIED`、`PLATFORM_OBSERVED`（页面观测、未通过核验）、`MOCK_DEMO`。
2. 生产求解只接受 `OWNER_VERIFIED`；`PLATFORM_OBSERVED` 可以进入 `offers.json` 与证据展示，但不得参与求解。
3. 三类来源的计数分离：`verifiedCount` 只统计 `OWNER_VERIFIED`，`mockCount` 只统计 `MOCK_DEMO`，页面观测单独计数。
4. 必须修复既有降级路径：重试时不得静默退到未核验价；`candidate_retriever` 的 `verified_only` 改为显式配置项。

## 考虑过的替代方案

- **只保留两值，采集结果直接写 `OWNER_VERIFIED`**：语义被稀释，无法区分人工核验与程序观测，也无法衡量真实核验覆盖率。
- **不扩展枚举，另加 `verification_level` 字段**：`price_source` 与 `verification_level` 会出现非法组合，需要额外一致性约束。
- **让求解器同时接受两类来源，仅在前端标注**：会把未核验价格当成真实成本参与预算求解，直接违背价格真实性要求。

## 影响

- `Offer`、`OfferFixture`、`OfferResponse`、`offers.json`、Agent `get_verified_offers` schema 与前端展示必须同步新增取值。
- 演示数据与页面观测数据都不能让一次配置「求解成功」，缺少核验报价时必须如实返回无解原因。
- 该决策与 [ADR 0011](0011-manually-verified-offer-dataset.md) 的「人工核验」前提存在张力：一旦取消人工核对，必须在 ADR 0011 之外另行定义核验规则，否则 `OWNER_VERIFIED` 将无人可达。
