# PC 配置数据质量与生命周期

| 项 | 内容 |
| --- | --- |
| 状态 | 已验证（对照 2026-11-08 分支源码与夹具） |
| 最后核验 | 2026-11-08 |
| 权威性 | 本文件描述数据质量、生命周期、推荐可用性与快照生命周期；三个状态字段的判定以 `Hardware.java` 为准，术语见 [glossary.md](./glossary.md) |
| 主要证据 | `pcbuild/domain/Hardware.java`、`Offer.java`、`HardwareCatalogService.java`、`BuildSolveService.java`、`BuildSnapshotService.java`、`V24__create_pc_build_snapshots.sql` |

## 1. 三个状态字段

`Hardware` 只读取 `dataQualityStatus`、`lifecycleStatus`、`recommendationStatus` 三个字符串，不做枚举校验。

| 字段 | 当前取值 | 对求解的影响 |
| --- | --- | --- |
| `data_quality_status` | `VERIFIED_STRUCTURED`、`PARTIAL` | 不参与 `isSolverEligible`；`PARTIAL` 仍可进入候选池，但缺失字段会让相关规则返回 `UNKNOWN` |
| `lifecycle_status` | `CURRENT` | 代码把 `DISCONTINUED` 与 `EOL` 视为退役；当前夹具没有这两个值 |
| `recommendation_status` | `ELIGIBLE` | 只有大小写不敏感的 `ELIGIBLE` 可进入候选池；`build_fixtures.py` 遇到 `BLOCKED` 会拒绝生成 |

进入候选池的判定是 `recommendation_status=ELIGIBLE` 且 `lifecycle_status` 不属于 `DISCONTINUED` / `EOL`。`data_quality_status` 只用于披露，不作为过滤器。

## 2. 数据质量如何传导到兼容性

- 3 款机箱的 `data_quality_status=PARTIAL`，`unverified_fields=["max_cooler_height_mm"]`；它们仍是 `ELIGIBLE`，会正常参与求解。
- 规格缺失时 `HardwareSpecifications` 对应字段为 `null`；`CompatibilityValidator` 遇到 `null` 必须返回 `UNKNOWN`，不得当作 `PASS`，也不得跳过规则。
- 因为机箱没有 `max_cooler_height_mm`，`cooler_case_height` 当前恒为 `UNKNOWN`；`CompatibilityReport.aggregate` 取最严重状态，所以整套方案 `overallStatus` 也是 `UNKNOWN`，即使其余 7 条为 `PASS`。
- `UNKNOWN` 不是硬冲突：求解器只把 `FAIL` 当失败，因此方案仍可生成；但前端与 Agent 不得把 `UNKNOWN` 展示成已兼容。

## 3. 报价可用性

`Offer.isUsableOn(asOf)` 同时满足以下条件才可参与求解：

| 条件 | 说明 |
| --- | --- |
| `price_fen > 0` | 金额必须是正整数分 |
| `match_status` 为 `VERIFIED` 或 `MOCK` | 其他状态（含 `PENDING`）不可用 |
| 未过期 | `valid_until` 为空视为长期有效；否则不得早于 `asOf` |
| `hardware_id` 非空 | 报价必须挂到硬件上 |

求解时 `asOf` 取 `LocalDate.now()`；`requireVerifiedOffers=true` 时再按 `price_source=OWNER_VERIFIED` 过滤。同一硬件有多条可用报价时取最低价，价格相同按 `offer_id` 升序，保证确定性。

## 4. `MOCK_DEMO` 标记规则

| 字段 | MOCK 条目取值（省略时由脚本填默认值） |
| --- | --- |
| `platform` | `MOCK_DEMO` |
| `seller` / `shop_name` | `演示数据` / `演示数据（非真实在售）` |
| `purchase_url` / `verified_at` / `valid_until` | 均为 `null` |
| `match_status` / `price_source` | `MOCK` / `MOCK_DEMO` |
| `price_type` | `NORMAL` |

`ingest_offers.py` 按 MOCK 条数写整体状态：无 MOCK 为 `OWNER_VERIFIED`，否则为 `MIXED_DEMO`。模板中的 `PENDING` 条目会被跳过并计入 `skipped_pending`，不会进入 `offers.json`。

当前 18 条 MOCK 分布：主板 2、内存 4、存储 3、散热 3、机箱 3、电源 3；它们没有有效期，因此在被替换前会一直可参与求解，这是已知的演示期风险。

## 5. 快照生命周期

- 只在求解成功后写入，且与求解处于同一事务；求解失败不写库。
- 每次成功生成新的 `build_id`（随机 UUID）与 `created_at`；表为 append-only，不更新、不删除。
- 读取必须同时匹配 `build_id` 与 `user_id`；不存在或不属于当前用户统一返回 `40302 BUILD_NOT_FOUND`，不泄露存在性。
- 快照保留当时的 `catalog_version`、`solver_version`、`compatibility_rule_version`、`offer_snapshot`，用于判断历史结果是否可比较。
- `parent_build_id` 列已建但写入恒为 `null`，父子追溯【未实现】。

## 6. 数据刷新与失效流程

1. 在京东自营或品牌官方旗舰店重新核验价格，更新模板中的 `price_cny`、`verified_at`、`valid_until`（当前人工核验价为 7 天窗口）。
2. 运行 `python scripts/pc-config/ingest_offers.py`，校验通过后覆写 `application-service/src/main/resources/pc-config/offers.json`。
3. 修改 catalog 或 benchmarks 时，先递增 `catalog_version`，再运行 `build_fixtures.py`，最后重启 Java。
4. 重启 application-service，使启动期夹具缓存重新加载；旧快照不会被回填或迁移。
5. 已过期报价在下一次求解时自动被 `isUsableOn` 排除；如果某类别因此没有可用报价，求解返回 `NO_CANDIDATES`。

## 7. 【未实现】

- 报价自动过期清理或定时抓取；目前依赖人工重跑脚本。
- 夹具版本化、回滚与变更审计；`catalog_version` 只是字符串，没有历史归档。
- 生命周期状态自动流转（如自动标记 `EOL`）与数据质量自动升级。
- 快照的保留期、归档与物理清理策略。
- `parent_build_id` 写入、方案对比与硬件替换链路。
