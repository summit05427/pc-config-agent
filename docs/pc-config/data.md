# PC 配置数据、质量与治理

| 项 | 内容 |
| --- | --- |
| 适用范围 | 运行时三份夹具、`pc_build_snapshots`、报价可用性、数据质量与离线治理产物 |
| 状态 | Current |
| 最后更新 | 2026-11-17 |
| 权威性 | 本文描述数据事实；接口字段以 [docs/api-contract.md](../api-contract.md) §5.7 为准，术语见 [glossary.md](./glossary.md) |
| 主要证据 | `application-service/src/main/resources/pc-config/*.json`、`pcbuild/domain/*.java`、`V24__create_pc_build_snapshots.sql`、`data/pc-config/manifest/catalog-manifest.json` |

## 1. 三份运行时夹具

| 文件 | 读取方 | 内容 |
| --- | --- | --- |
| `pc-config/catalog.json` | `JsonHardwareCatalogRepository` | 硬件、规格、数据质量状态与 `catalog_version` |
| `pc-config/benchmarks.json` | `JsonBenchmarkRepository` | CPU / GPU / 存储跑分 |
| `pc-config/offers.json` | `JsonOfferRepository` | 中国区商品报价与整体 `data_status` |

三者由 `JsonFixtureLoader` 在启动期读入并缓存；文件缺失抛 `40305 CATALOG_UNAVAILABLE`，解析失败阻止启动。修改夹具后必须重启 Java；热加载与刷新接口【未实现】。

## 2. 当前规模（2026-11-17 实测）

| 项 | 值 |
| --- | --- |
| 硬件目录 | **402** 款 |
| 类别分布 | CPU 71 / GPU 66 / 主板 60 / 内存 60 / 存储 53 / 电源 40 / 机箱 26 / 散热 26 |
| 报价 | **402** 条，覆盖 402 个 `hardware_id`，与目录一一对应 |
| `data_status` | `PLATFORM_OBSERVED_ONLY` |
| `price_source` | `PLATFORM_OBSERVED` 402，`OWNER_VERIFIED` 0，`MOCK_DEMO` 0 |
| `match_status` | `OBSERVED` 402 |
| 跑分 `entries` | **169** 条：CPU 71（`CPUMARK`）、GPU 66（`G3D_MARK`）、存储 32（`DISKMARK`） |
| 跑分 `unmatched` | 21 条 |
| `catalog_version` | `2026.11.2` |

## 3. `catalog.json`

顶层键：`schema_version`、`catalog_version`、`generated_at`、`source`、`platform_pairs`、`hardware`。

`hardware[]` 字段：

| 字段 | 说明 |
| --- | --- |
| `hardware_id` | 稳定主键，报价与跑分通过它关联 |
| `category` | `CPU` / `MOTHERBOARD` / `MEMORY` / `GPU` / `PSU` / `CASE` / `COOLER` / `STORAGE` |
| `brand` / `model_name` / `display_name` | 品牌、标准型号、展示名 |
| `specifications` | 扁平规格对象，缺失值为 `null` |
| `source` | 数据集、来源链接、参考价等；参考价不参与预算 |
| `data_quality_status` | `VERIFIED_STRUCTURED` / `PARTIAL` / `BLOCKED` |
| `lifecycle_status` | `CURRENT` / `MATURE` / `LEGACY` / `UNKNOWN` 等 |
| `recommendation_status` | `ELIGIBLE` / `RESTRICTED` 等 |
| `unverified_fields` | 未核验字段名数组 |
| `selection_reason` | 入选理由，仅展示 |
| `price_cny` / `price_source` / `price_status` / `price_confidence` / `price_note` / `price_source_url` | 目录参考价及其来源；**不参与运行时报价与预算** |
| `popularity_status` / `stratum` | 运营分层字段，不参与选型 |

当前数据质量分布：`VERIFIED_STRUCTURED` 333、`PARTIAL` 68、`BLOCKED` 1；推荐资格 `ELIGIBLE` 401、`RESTRICTED` 1。兼容字段缺失：26 款机箱中 20 款缺 `max_cooler_height_mm`，26 款散热中 11 款缺 `height_mm`。

## 4. `specifications` 实际键

| 类别 | 键 |
| --- | --- |
| CPU | `socket`、`platform`、`core_count`、`thread_count`、`tdp_w`、`integrated_graphics`、`includes_cooler`、`max_memory` |
| GPU | `chipset`、`vram_gb`、`memory_type`、`tdp_w`、`length_mm`、`slot_width`、`external_power{connector_type,count}` |
| MOTHERBOARD | `socket`、`platform`、`form_factor`、`chipset`、`memory_type`、`memory_slots`、`max_memory_speed_mts`、`m2_slot_count`、`sata_ports`、`pcie_x16_slots` |
| MEMORY | `memory_type`、`capacity_gb`、`module_count`、`module_size_gb`、`speed_mts`、`form_factor`、`cas_latency` |
| STORAGE | `capacity_gb`、`interface`、`form_factor`、`nvme` |
| COOLER | `cooler_type`、`height_mm`、`radiator_size_mm`、`supported_sockets`、`fanless` |
| CASE | `supported_mainboard_form_factors`、`max_gpu_length_mm`、`max_cooler_height_mm`、`psu_form_factor`、`radiator_support`、`expansion_slots` |
| PSU | `wattage_w`、`efficiency`、`modular`、`form_factor`、`pcie_8pin_count`、`pcie_12vhpwr_count`、`length_mm`、`sata_connectors` |

## 5. `benchmarks.json`

顶层：`schema_version`、`generated_at`、`source`、`entries`、`unmatched`。

条目字段：`hardware_id`、`benchmark_type`、`score`、`secondary_score`、`rank_no`、`samples`、`source`、`match_method`、`match_confidence`。

内存 / 主板 / 电源 / 机箱 / 散热无跑分；缺失时语言层不引用跑分，不影响组装。

## 6. `offers.json`

顶层：`schema_version`、`generated_at`、`data_status`、`currency`（`CNY`）、`price_unit`（`CNY_FEN`）、`catalog_version`、`offers`、`verified_offer_count`、`mock_offer_count`、`observed_offer_count`、`skipped_pending`。

条目字段：`offer_id`、`hardware_id`、`category`、`platform`、`seller`、`shop_name`、`title`、`platform_sku`、`price_fen`、`price_type`、`purchase_url`、`verified_at`、`valid_until`、`match_status`、`price_source`、`notes`。

- 当前全部为平台观测价，**没有人工逐件核验价**；`verified_offer_count=0`。
- `PLATFORM_OBSERVED` 只能表述为「参考价（平台观测，未经人工核验）」，不得说成已核验。
- `offers.json` 是价格唯一运行时出口；`catalog.json` 中的参考价只供人工核对，不参与预算。

## 7. 报价可用性与取价

`Offer.isUsableOn(asOf)` 需同时满足：

| 条件 | 说明 |
| --- | --- |
| `price_fen > 0` | 正整数分 |
| `match_status` 为 `VERIFIED`、`MOCK` 或 `OBSERVED` | 其他状态不可用 |
| 未过期 | `valid_until` 为空视为长期有效；否则不得早于 `asOf` |
| `hardware_id` 非空 | 必须挂到硬件上 |

同一硬件多条可用报价取最低价；价格相同按 `offer_id` 升序。`require_verified_offers=true` 时只接受 `price_source=OWNER_VERIFIED`，当前会因无核验价而失败。

## 8. 快照表 `pc_build_snapshots`

| 列 | 类型 / 约束 | 用途 |
| --- | --- | --- |
| `build_id` / `user_id` | PK / NOT NULL | 方案标识；`user_id` 为 JWT `sub` |
| `parent_build_id` | `uuid` NULL，自引用 | 预留；当前恒为 `null`【未实现】 |
| `requirements_snapshot` / `components` | `jsonb` NOT NULL | 需求与 8 类组件快照 |
| `total_price_fen` / `budget_max_fen` | `bigint`（非负） | 总价与预算上限，单位分 |
| `compatibility_report` | `jsonb` NOT NULL | 9 条规则结论与 `ruleVersion` |
| `benchmark_snapshot` / `offer_snapshot` | `jsonb` NOT NULL | 选用跑分与报价 |
| `solver_version` / `compatibility_rule_version` | `varchar(32)` | 组装器与规则版本 |
| `catalog_version` / `created_at` | `varchar(64)` / `timestamptz` | 目录版本与创建时间 |

索引为 `(user_id, created_at DESC)` 与 `(parent_build_id)`。表为 append-only：只插入，不更新、不删除。读取同时匹配 `build_id` 与 `user_id`，越权或不存在统一返回 `40302`。

## 9. 状态字段与兼容性传导

| 字段 | 当前取值 | 对流程的影响 |
| --- | --- | --- |
| `data_quality_status` | `VERIFIED_STRUCTURED`、`PARTIAL`、`BLOCKED` | 不直接阻断；`PARTIAL` 缺失字段会让相关规则返回 `UNKNOWN` |
| `lifecycle_status` | 以 `CURRENT` / `MATURE` 为主 | `DISCONTINUED` / `EOL` 不再推荐 |
| `recommendation_status` | `ELIGIBLE` 401、`RESTRICTED` 1 | 只有 `ELIGIBLE` 进入候选 |

`CompatibilityValidator` 遇到 `null` 必须返回 `UNKNOWN`，不得跳过规则或当作 `PASS`。机箱限高缺失使 `cooler_case_height` 常为 `UNKNOWN`，整套方案 `overallStatus` 也随之 `UNKNOWN`。

## 10. 离线治理产物（`data/pc-config/`）

治理产物**尚未接入 Java 运行时**；运行时仍读取 classpath 夹具。

| 项 | 实测值 |
| --- | --- |
| 主数据 `hardware-master.jsonl` | 8,238 条 |
| 跑分映射 `hardware-benchmarks.jsonl` | 3,557 条（MATCHED 1,942 / UNMATCHED 1,610 / AMBIGUOUS 5） |
| 重复线索 | 2,203 条 |
| 冲突组 | 473 组 |
| 发布候选池 | standard 4,107 / budget 7,200 / legacy 1,197 / archived 142 |
| 批次 / 版本 | `20261109T000000Z-3d66ed` / `catalog_version=2026.11.0` |
| 分发状态 | `INTERNAL_ONLY` |

详见 [硬件主数据治理报告](../quality/hardware-data-governance-report.md)。

## 11. 更新入口

| 数据 | 入口 |
| --- | --- |
| catalog / benchmarks | `scripts/data-cleaning/export_runtime_catalog.py`（前置短名单与跑分映射脚本）→ `application-service/src/main/resources/pc-config/` |
| offers | `scripts/data-cleaning/build_offers_from_shortlist.py` → 同一 resources 目录 |
| 候选范围 | `data/pc-config/cleaning/stage4-shortlist.jsonl`（当前 402 条） |

刷新步骤：追加价格观测 → 依次运行短名单、观测应用、fallback、跑分映射、目录导出 → 生成 offers → 重启 application-service。旧快照不回填。

## 12. 未实现

- 报价自动采集、过期清理与价格历史。
- 夹具版本化、回滚与变更审计。
- 治理主数据接入运行时与 `OfferRepository`。
- 快照保留期、归档与 `parent_build_id` 写入。

## 13. 常见误用

- 把 `price_cny` 当运行时价格，或用浮点金额。
- 把 `PLATFORM_OBSERVED` 当已核验价。
- 用 `reference_price` 判断预算。
- 把 `PENDING` 写进运行时夹具。
- 把 `market_status=UNVERIFIED` 当成 `EOL`。
