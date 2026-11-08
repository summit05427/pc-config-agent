# PC 配置内部接口契约（工作索引）

| 项 | 内容 |
| --- | --- |
| 状态 / 最后核验 | Completed / 2026-11-08 |
| 权威性 | 工作索引；字段与语义的最终事实源是根 [`docs/api-contract.md`](../api-contract.md) §5.7 与 §7，冲突时以根契约为准 |
| 主要证据 | `PcBuildInternalController`、`PcHardwareInternalController`、`web/dto/**`、`PcBuildErrorCode`；`agent-service/app/agent/pc/renderer.py`；`agent-service/app/services/turn.py`；`frontend/src/features/sessions/api/build-result.ts` |

## 1. 通用约定
- 七个接口只允许 Agent 经容器内网直连；鉴权为服务令牌，用户维度另带 `X-User-Token`。响应由 `ApiResponse` 包装（成功 `code=0`）；金额一律人民币整数分，错误码 `40301`–`40306`，公共参数错误为 `400 10001`。

## 2. GET /internal/v1/pc/hardware/candidates
- 鉴权：服务令牌。请求：`category`（query，可选，八类之一）。
- 响应 `data`：`catalogVersion`、`total`、`list[]`；详情接口复用同一硬件字段表。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `hardwareId` | string | 是 | 稳定硬件标识 |
| `category` | enum | 是 | 八类之一 |
| `brand` / `modelName` / `displayName` | string | 是 | 品牌、型号、展示名 |
| `specifications` | object | 是 | 规格对象；缺失字段不输出 |
| `specSummary` | string | 是 | 单行规格摘要 |
| `dataQualityStatus` / `lifecycleStatus` / `recommendationStatus` | string | 是 | 数据质量与生命周期状态 |

- 错误：未知 `category` → `400 10001`；缺服务令牌 → 安全层 `401`。
## 3. GET /internal/v1/pc/hardware/{hardwareId}
- 鉴权：服务令牌。路径参数 `hardwareId`（string，必填）。
- 响应：单个硬件对象，字段同 §2 表。错误：不存在 → `404 40301`。
## 4. GET /internal/v1/pc/benchmarks
- 鉴权：服务令牌。请求：`hardwareId`、`category` 均可选；传 `hardwareId` 时忽略 `category`。
- 响应 `data`：`total`、`list[]`。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `hardwareId` / `benchmarkType` | string | 是 | 硬件与基准类型 |
| `score` | number | 是 | 主分数 |
| `secondaryScore` / `rankNo` / `samples` | number \| null | 否 | 附加指标 |
| `matchMethod` / `matchConfidence` / `sourceName` | string/number \| null | 否 | 来源与匹配置信度 |

- 行为：无数据返回空列表，不猜测分数；未知 `category` → `400 10001`。
## 5. GET /internal/v1/pc/offers
- 鉴权：服务令牌。请求：`hardwareId`、`category`、`verifiedOnly`（默认 `false`；为 `true` 时只返回 `matchStatus=VERIFIED`）。
- 响应 `data`：`dataStatus`、`priceUnit`（固定 `CNY_FEN`）、`verifiedOfferCount`、`mockOfferCount`、`total`、`list[]`。

| 字段组 | 字段 | 说明 |
| --- | --- | --- |
| 标识 | `offerId`、`hardwareId`、`category`、`matchStatus` | 商品与匹配状态 |
| 金额 | `priceFen`、`priceType`、`priceSource`、`verifiedPrice` | 整数分；`MOCK_DEMO` 不是已核验价 |
| 商家 | `platform`、`seller`、`shopName`、`title`、`platformSku`、`purchaseUrl` | 演示价通常无链接 |
| 时效 | `verifiedAt`、`validUntil`、`notes` | 核验与有效期 |

- 错误：未知 `category` → `400 10001`。
## 6. POST /internal/v1/pc/builds/solve
- 鉴权：服务令牌 + `X-User-Token`（缺失/无效 → `401 40306`）；用户身份只从令牌 `sub` 解析。
- 请求体：

| 字段 | 类型 | 必填 | 校验与语义 |
| --- | --- | --- | --- |
| `budgetMaxFen` | integer | 否 | `>= 0`；为空表示无硬预算 |
| `scenario` | string | 否 | 8 个入参别名；缺省 `BALANCED` |
| `minMemoryGb` / `minStorageGb` | integer | 否 | 1–512 / 1–8192 |
| `requireVerifiedOffers` | boolean | 否 | 默认 `false`；为 `true` 时不接受演示价 |

- 响应 `data`：`solved`、`build`（成功时）、`failure`（失败时）。`solved=false` 仍是 HTTP 200 的正常业务结果，**调用方不得自行放宽预算**。
- `scenario` 入参：`GAMING`/`VIDEO_EDITING`/`CREATIVE`/`PROGRAMMING`/`WORKSTATION`/`OFFICE`/`GENERAL_USE`/`BALANCED`；响应归一化为 6 个领域值（`VIDEO_EDITING`→`CREATIVE`，`GENERAL_USE`→`BALANCED`）。
- `failure`：`reason`（`NO_CANDIDATES`/`NO_COMPATIBLE_BUILD`/`BUDGET_EXCEEDED`）、`message`、`missingCategories[]`、`candidateCounts{}`、`minimumRequiredBudgetFen`、`evaluatedCombinationCount`。
- 错误：场景不在 8 个合法值时首先被 `@Pattern` 拦截为 `400 10001`；DTO 转换仍无法识别（防御分支）为 `400 40304`；目录不可用为 `503 40305`。
## 7. POST /internal/v1/pc/builds/validate
- 鉴权：仅服务令牌（不要求 `X-User-Token`），不落库。
- 请求体八字段均 `@NotBlank`：`cpu`、`motherboard`、`memory`、`gpu`、`psu`、`case`（JSON 名）、`cooler`、`storage`。
- 响应 `data`：`valid`（是否存在 `FAIL`）、`report.ruleVersion`、`report.overallStatus`、`report.hasFailure`、`report.checks[]`；check 为 `ruleId`、`ruleName`、`status`、`message`、`hardwareIds[]`。
- 语义：`UNKNOWN` 不影响 `valid`，但绝不能展示为 `PASS`。错误：空字段先由 `@NotBlank` 拦截为 `400 10001`；类别不符或 DTO 转换缺类别为 `400 40303`；硬件不存在 → `404 40301`。
## 8. GET /internal/v1/pc/builds/{buildId}
- 鉴权：服务令牌 + `X-User-Token`。路径参数 `buildId`（UUID）。
- 响应：`BuildResultResponse`，字段见 §9。错误：不存在或不属于当前用户 → `404 40302`；缺用户令牌 → `401 40306`。
## 9. 公共响应结构（solve 成功与快照读取）

| 对象 | 字段 |
| --- | --- |
| `build` | `buildId`、`requirements`、`components[]`、`totalPriceFen`、`budgetMaxFen`、`budgetStatus`、`compatibilityReport`、`solverVersion`、`compatibilityRuleVersion`、`catalogVersion`、`offerDataStatus`、`verifiedOfferCount`、`demoOfferCount`、`createdAt` |
| `requirements` | `budgetMaxFen`、`scenario`（6 个领域值）、`minMemoryGb`、`minStorageGb`、`requireVerifiedOffers` |
| `components[]` | `category`、`hardwareId`、`brand`、`modelName`、`specSummary`、`title`、`priceFen`、`priceSource`、`priceType`、`verifiedPrice`、`purchaseUrl`、`platform`、`seller`、`offerId`、`matchStatus`、`verifiedAt`、`validUntil`、`benchmarkType`、`benchmarkScore` |
| `compatibilityReport` | `ruleVersion`、`overallStatus`（`PASS`/`WARNING`/`FAIL`/`UNKNOWN`）、`hasFailure`、`checks[]`（结构同 §7） |
| `budgetStatus` | 当前枚举仅 `WITHIN_BUDGET`、`NO_BUDGET`；求解器不返回超预算方案 |

## 10. `done.build_result`（仅 success 时出现，snake_case）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `build_id` | string \| null | 快照 ID |
| `components[]` | array | `category`、`model_name`、`brand`、`title`、`platform`、`seller`、`price_source`、`spec_summary`、`price_fen`、`purchase_url`、`benchmark{type,score}`、`offer_verified_at` |
| `total_price_fen` / `budget_max_fen` / `budget_status` | integer / integer / string | 总价、预算上限、预算结论 |
| `compatibility[]` / `overall_status` | array/string | 逐条 `rule`、`status`、`message` 与总状态 |
| `demo_offer_count` | integer | 演示价条数；大于 0 时前端常驻提示 |
| `reason_summary` | string | 推荐说明；权威正文仍是 `token` 事件 |

## 11. 跨端同步要求
- Java DTO：`application-service/src/main/java/com/example/agent/pcbuild/web/dto/**`；字段改名视为契约变更。
- Agent：`app/agent/pc/schemas.py`、`renderer.py`、`nodes.py`；内部 camelCase，输出时转 snake_case。前端：`frontend/src/features/sessions/api/types.ts`、`build-result.ts`，解析器容忍两种命名并降级未知状态。
- 契约基线：`agent-service/tests/contracts/sse_events.json`；字段集合或 `schema_version` 变更必须显式更新快照；变更顺序为先改根 [`docs/api-contract.md`](../api-contract.md)，再同步 Java DTO、Agent 投影、前端类型与测试，最后更新本索引。
