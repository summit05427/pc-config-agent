# PC 配置数据、质量与治理

| 项 | 内容 |
| --- | --- |
| 状态 | 已验证（对照 2026-11-11 分支夹具与 `data/pc-config/` 实测） |
| 最后核验 | 2026-11-11 |
| 权威性 | 本文件描述运行时三份夹具、`pc_build_snapshots`、数据质量与生命周期规则，以及 Stage 8 离线治理产物；HTTP 字段以 [api-contract.md](../api-contract.md) §5.7 为准，术语见 [glossary.md](./glossary.md) |
| 主要证据 | `application-service/src/main/resources/pc-config/*.json`、`application-service/.../pcbuild/domain/*.java`、`V24__create_pc_build_snapshots.sql`、`scripts/pc-config/`、`data/pc-config/` |

## 1. 三份运行时夹具与加载

| 文件 | 读取方 | 内容 |
| --- | --- | --- |
| `pc-config/catalog.json` | `JsonHardwareCatalogRepository` | 硬件、规格、数据质量状态与 `catalog_version` |
| `pc-config/benchmarks.json` | `JsonBenchmarkRepository` | CPU / GPU 的 PassMark 跑分 |
| `pc-config/offers.json` | `JsonOfferRepository` | 中国区商品报价与整体 `data_status` |

三者由 `JsonFixtureLoader` 在启动期读入并缓存；文件缺失抛 `40305 CATALOG_UNAVAILABLE`，解析失败阻止启动。修改夹具后必须重启 Java，热加载与运行时刷新接口【未实现】。

## 2. `catalog.json` 顶层

| 键 | 类型 / 当前值 | 用途 |
| --- | --- | --- |
| `catalog_version` | `"2026.11.2"` | 随快照落库，用于判断历史方案可比性 |
| `platform_pairs` | 数组，当前 0 条 | 平台对照预留字段，求解不读取 |
| `hardware` | 对象数组，当前 402 条 | 硬件主数据，见 §3 |

> 2026-11-12 实测：顶层为 `schema_version`、`catalog_version`、`generated_at`、`source`、`platform_pairs`、`hardware`；早期文档中的 `source{raw_rows}` 已不存在，不得再引用 `raw_rows=28` 或 `2026-11-08-demo-1`。

## 3. `hardware[]` 条目

| 字段 | 说明 |
| --- | --- |
| `hardware_id` | 稳定主键，报价与跑分通过它关联 |
| `category` | `CPU` / `MOTHERBOARD` / `MEMORY` / `GPU` / `PSU` / `CASE` / `COOLER` / `STORAGE` |
| `brand` / `model_name` / `display_name` | 品牌、标准型号、展示名 |
| `specifications` | 扁平规格对象，缺失值为 `null`，见 §4 |
| `source` | 含 `dataset`、`pcpp_id`、`source_url`、`image_url`、`reference_price`、`reference_price_note`；参考价不参与预算 |
| 状态三字段 | `data_quality_status`（`VERIFIED_STRUCTURED` / `PARTIAL`）、`lifecycle_status`（当前 `CURRENT`）、`recommendation_status`（当前 `ELIGIBLE`）；后两者决定是否进入候选池 |
| `unverified_fields` | 未核验字段名数组；3,969 条为空，5 款机箱为 `["max_cooler_height_mm"]` |
| `selection_reason` | 入选理由，仅展示 |

当前类别分布：CPU 71、GPU 289、主板 512、内存 1,108、存储 215、散热 589、机箱 822、电源 368。

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

顶层为 `schema_version`、`generated_at`、`source{name,snapshot_date}`、`entries`、`unmatched`。条目字段：`hardware_id`、`benchmark_type`（CPU 为 `CPUMARK`，GPU 为 `G3D_MARK`）、`score`、`secondary_score`、`rank_no`、`samples`、`source{name,source_id,source_name,snapshot_date}`、`match_method`、`match_confidence`。

当前 `entries` 169 条、`unmatched` 21 条：CPU 71（`CPUMARK`）、GPU 66（`G3D_MARK`）、存储 32（`DISKMARK`）。内存 / 主板 / 电源 / 机箱 / 散热无跑分，求解不依赖。缺失跑分时评分为 0，不阻断求解。

## 6. `offers.json`

顶层：`schema_version`、`generated_at`、`data_status`、`currency`（`CNY`）、`price_unit`（`CNY_FEN`）、`catalog_version`、`offers`、`verified_offer_count`、`mock_offer_count`、`observed_offer_count`、`skipped_pending`。

条目字段：`offer_id`、`hardware_id`、`category`、`platform`、`seller`、`shop_name`、`title`、`platform_sku`、`price_fen`、`price_type`、`purchase_url`、`verified_at`、`valid_until`、`match_status`、`price_source`、`price_basis`、`observed_at`、`provider`、`availability_status`、`verification_method`、`notes`。

2026-11-12 实测：

| 维度 | 分布 |
| --- | --- |
| 总量 | 402 条，覆盖 402 个 `hardware_id`（与 catalog 一一对应）；`data_status=PLATFORM_OBSERVED_ONLY` |
| `price_source` | `PLATFORM_OBSERVED` 402（含人工逐件核验前的观测价与估算价） |
| `match_status` | 全部 `OBSERVED` |
| `verified_at` | 243 条有值（对应 `OBSERVED_2026-11-11`），其余为空（估算价） |
| `valid_until` | 观测价 2027-02-12，估算价 2026-12-12 |

`offers.json` 现在由 `scripts/data-cleaning/build_offers_from_shortlist.py` 从 Stage 4 短名单生成，是价格的唯一运行时出口：`catalog.json` 里的 `price_cny` 仅供人工核对，Java 求解器只读 `offers.json`。`data_status` 为 `PLATFORM_OBSERVED_ONLY` 表示当前没有任何人工逐件核验报价。

> 以下 `price_basis` / `WEB_ANCHOR` / 合并优先级属于旧 Stage-8 流水线（`scripts/pc-config/`）的语义，当前 `build_offers_from_shortlist.py` 不写 `price_basis`，也不做多来源合并；保留本节仅为读旧快照时对照。

`price_basis` 允许值新增 `WEB_ANCHOR`：由 `scripts/pc-config/web_price_anchors.py` 把 WebSearch 记录的区间展开为参考价，`price_fen` 取区间中点，`notes` 保留区间、检索词与来源数。优先级为 `SKU_PANEL > LISTING_MATCH > SEARCH_LIST > WEB_ANCHOR > BUCKET > FALLBACK`，锚点不会覆盖任何详情页观测。

## 7. 关系与金额

- `hardware` 1:N `offers`；`hardware_id` 必须在 catalog 中存在，脚本生成时校验，运行时不再校验。
- `hardware` 0..1 `benchmark`，仅 CPU / GPU 有；缺失时评分按 0 处理。
- 运行时金额一律是 `long` 整数分（`price_fen`、`total_price_fen`、`budget_max_fen`）；模板中的 `price_cny` 只是录入单位，由脚本换算。
- `offers.json` 的 `catalog_version` 应与 catalog 一致；快照同时记录 `catalog_version`、`solver_version`、`compatibility_rule_version`。

## 8. 快照表 `pc_build_snapshots`

| 列 | 类型 / 约束 | 用途 |
| --- | --- | --- |
| `build_id` / `user_id` | PK / NOT NULL | 方案标识；`user_id` 为 JWT `sub`，读取时校验归属 |
| `parent_build_id` | `uuid` NULL，自引用 | 预留父快照；当前写入恒为 `null`【未实现】 |
| `requirements_snapshot` / `components` | `jsonb` NOT NULL | 需求与八类组件快照 |
| `total_price_fen` / `budget_max_fen` | `bigint`（非负） | 总价与预算上限，单位分；预算可空 |
| `compatibility_report` | `jsonb` NOT NULL | 九条规则结论与 `ruleVersion` |
| `benchmark_snapshot` / `offer_snapshot` | `jsonb` NOT NULL | 选用跑分与报价（含 `data_status`） |
| `solver_version` / `compatibility_rule_version` | `varchar(32)` | 求解器与规则版本 |
| `catalog_version` / `created_at` | `varchar(64)` / `timestamptz` | 目录版本与创建时间 |

索引为 `(user_id, created_at DESC)` 与 `(parent_build_id)`。表为 append-only：只插入，不更新、不删除。

## 9. 三个状态字段与数据质量传导

`Hardware` 只读取 `dataQualityStatus`、`lifecycleStatus`、`recommendationStatus` 三个字符串，不做枚举校验。

| 字段 | 当前取值 | 对求解的影响 |
| --- | --- | --- |
| `data_quality_status` | `VERIFIED_STRUCTURED`、`PARTIAL` | 不参与 `isSolverEligible`；`PARTIAL` 仍可进入候选池，但缺失字段会让相关规则返回 `UNKNOWN` |
| `lifecycle_status` | `CURRENT` | 代码把 `DISCONTINUED` 与 `EOL` 视为退役；当前夹具没有这两个值 |
| `recommendation_status` | `ELIGIBLE` | 只有大小写不敏感的 `ELIGIBLE` 可进入候选池；`build_fixtures.py` 遇到 `BLOCKED` 会拒绝生成 |

- 3,969 条硬件 `data_quality_status=VERIFIED_STRUCTURED`；5 款机箱为 `PARTIAL`，`unverified_fields=["max_cooler_height_mm"]`，它们仍是 `ELIGIBLE`，会正常参与求解。
- 规格缺失时 `HardwareSpecifications` 对应字段为 `null`；`CompatibilityValidator` 遇到 `null` 必须返回 `UNKNOWN`，不得当作 `PASS`，也不得跳过规则。
- 因为机箱缺少 `max_cooler_height_mm`，`cooler_case_height` 恒为 `UNKNOWN`；`CompatibilityReport.aggregate` 取最严重状态，所以整套方案 `overallStatus` 也是 `UNKNOWN`，即使其余 8 条为 `PASS`。
- `UNKNOWN` 不是硬冲突：求解器只把 `FAIL` 当失败，因此方案仍可生成；但前端与 Agent 不得把 `UNKNOWN` 展示成已兼容。

## 10. 报价可用性

`Offer.isUsableOn(asOf)` 同时满足以下条件才可参与求解：

| 条件 | 说明 |
| --- | --- |
| `price_fen > 0` | 金额必须是正整数分 |
| `match_status` 为 `VERIFIED` 或 `MOCK` | 其他状态（含 `PENDING`）不可用 |
| 未过期 | `valid_until` 为空视为长期有效；否则不得早于 `asOf` |
| `hardware_id` 非空 | 报价必须挂到硬件上 |

求解时 `asOf` 取 `LocalDate.now()`；`requireVerifiedOffers=true` 时再按 `price_source=OWNER_VERIFIED` 过滤。同一硬件有多条可用报价时取最低价，价格相同按 `offer_id` 升序，保证确定性。

> 当前 `requireVerifiedOffers` 默认 `false`，3,809 条 `PLATFORM_OBSERVED` 会参与求解，与「生产只用核验价」的决策存在偏差，见 [roadmap §5.4](../planning/roadmap.md) S9-05。

## 11. `MOCK_DEMO` 标记规则

| 字段 | MOCK 条目取值（省略时由脚本填默认值） |
| --- | --- |
| `platform` | `MOCK_DEMO` |
| `seller` / `shop_name` | `演示数据` / `演示数据（非真实在售）` |
| `purchase_url` / `verified_at` / `valid_until` | 均为 `null` |
| `match_status` / `price_source` | `MOCK` / `MOCK_DEMO` |
| `price_type` | `NORMAL` |

`ingest_offers.py` 按 MOCK 条数写整体状态：无 MOCK 为 `OWNER_VERIFIED`，否则为 `MIXED_DEMO`。模板中的 `PENDING` 条目会被跳过并计入 `skipped_pending`，不会进入 `offers.json`。

当前 18 条 MOCK 分布：主板 2、内存 4、存储 3、散热 3、机箱 3、电源 3；它们没有有效期，因此在被替换前会一直可参与求解，这是已知的演示期风险。

## 12. 快照生命周期

- 只在求解成功后写入，且与求解处于同一事务；求解失败不写库。
- 每次成功生成新的 `build_id`（随机 UUID）与 `created_at`；表为 append-only，不更新、不删除。
- 读取必须同时匹配 `build_id` 与 `user_id`；不存在或不属于当前用户统一返回 `40302 BUILD_NOT_FOUND`，不泄露存在性。
- 快照保留当时的 `catalog_version`、`solver_version`、`compatibility_rule_version`、`offer_snapshot`，用于判断历史结果是否可比较。
- `parent_build_id` 列已建但写入恒为 `null`，父子追溯【未实现】。

## 13. 治理状态与生命周期分类（Stage 8 离线产物）

本章描述 `data/pc-config/` 下的治理数据，**尚未接入 Java 运行时**；运行时仍读取 classpath 夹具，规则以 §1–§12 为准（[PC 配置模块决策合并记录](../adr/0027-pc-config-decisions.md) §3.5）。

### 13.1 五个独立状态字段

| 字段 | 取值 | 判定来源 |
| --- | --- | --- |
| `data_quality_status` | `VERIFIED_STRUCTURED`、`PARTIAL`、`BLOCKED` | 原 `evaluate_quality`，语义不变 |
| `governance_status` | `VALID`、`INCOMPLETE`、`INVALID`、`CONFLICT` | 字段完整性、重复与冲突审核结果 |
| `lifecycle_status` | `CURRENT`、`MATURE`、`LEGACY`、`DISCONTINUED`、`UNKNOWN` | 类别规则，见 §13.2 |
| `market_status` | `UNVERIFIED`、`AVAILABLE`、`EOL` | 市场在售证据；当前 8,238 条全部 `UNVERIFIED` |
| `recommendation_status` | `ELIGIBLE`、`RESTRICTED`、`EXCLUDED`、`ARCHIVED` | 由前四个字段按类别规则派生 |

五个字段互不覆盖。新增 `governance_status` 而不是改写 `data_quality_status`，避免破坏现有夹具与 Java 读取逻辑。

### 13.2 生命周期与推荐资格

- CPU 按 Socket 代际、GPU 按 Chipset 正则、主板按 Socket + Chipset、内存按 DDR 代际、存储按接口代际判定；散热、机箱、电源一律 `UNKNOWN`。
- 判定只使用结构化字段与参考表，禁止用 LLM 记忆补全。
- `UNKNOWN` 不等于 `EXCLUDED`：CPU/GPU 的 `UNKNOWN` 为 `RESTRICTED`；机箱/散热/电源只要兼容性关键字段齐全即可 `ELIGIBLE`。
- `CURRENT` 也不自动等于 `ELIGIBLE`：治理状态为 `INCOMPLETE` 时仍为 `RESTRICTED`。
- `DISCONTINUED` 或 `governance_status=INVALID` 为 `EXCLUDED`。
- 2026-11-11 实测：主数据 8,238 条；`recommendation_status` 为 `ELIGIBLE` 7,263、`RESTRICTED` 833、`EXCLUDED` 142；`lifecycle_status` 为 `CURRENT` 1,798、`MATURE` 2,319、`LEGACY` 1,197、`UNKNOWN` 2,782、`DISCONTINUED` 142。
- 跑分映射 3,557 条（`MATCHED` 1,942、`UNMATCHED` 1,610、`AMBIGUOUS` 5）；重复线索 2,203 条、冲突组 473 组，均保留在主数据并进入审核队列。
- 候选池：`standard` 4,107、`budget` 7,200、`legacy` 1,197、`archived` 142。每类 UNKNOWN 占比与逐类明细见 [硬件主数据治理报告](../quality/hardware-data-governance-report.md)。

### 13.3 产物清单

| 路径 | 权威性 | 说明 |
| --- | --- | --- |
| `master/hardware-master.jsonl` | 全量主数据（本地生成） | 8 类硬件，含 `raw_specs` 与五个状态字段；JSONL 是权威格式 |
| `master/hardware-benchmarks.jsonl` | 全量跑分映射（本地生成） | PassMark 映射，含 `match_method`、`match_confidence`、`match_scope` |
| `schema/*.schema.json` | 入库 | 公共字段与八类专属规格的 JSON Schema |
| `manifest/catalog-manifest.json` | 入库 | 发布批次、输入 `sha256`、脚本摘要、计数与分发状态 |
| `pools/*.jsonl` | 派生（本地生成） | 四类发布候选池，由主数据与跑分派生 |
| `export/third-party-mapping-input.json` | 派生（本地生成） | 第三方商品映射输入，回填字段为 `null` |

### 13.4 与运行时夹具的关系

- `data/pc-config/` 是离线治理主数据，`catalog.json` 仍是运行时唯一夹具，两者互不替换。
- 2026-11-12 起 `catalog.json` 已替换为 Stage 4 短名单产出的 402 条，`PcFixtureRepositoryTests` 也同步改过（`data_status` 断言为 `PLATFORM_OBSERVED_ONLY`）。`BuildSolver` 只接受有可用 offer 的硬件，因此候选池扩容必须同步生成 offers，否则新增型号不参与求解。
- `hardware_id` 规则与 `catalog.json` 完全一致；8,238 条主数据中仅 2,094 条因重名追加 `-<source_id>` 后缀，原 28 条基线 ID 不受影响。
- 原始 CSV 不进入仓库；`manifest.inputs` 用 `sha256` 标识输入版本。

## 14. 更新入口与刷新流程

| 数据 | 入口 |
| --- | --- |
| catalog / benchmarks | `scripts/data-cleaning/export_runtime_catalog.py`（前置 `stage4_hot_shortlist.py` → `apply_price_observations.py` → `stage4_price_fallback.py` → `build_benchmark_image_maps.py`）→ `application-service/src/main/resources/pc-config/` |
| offers | `scripts/data-cleaning/build_offers_from_shortlist.py`（读 Stage 4 短名单，`price_cny × 100 → price_fen`）→ 同一 resources 目录 |
| 候选范围 | `data/pc-config/cleaning/stage4-shortlist.jsonl`（当前 402 条，唯一价格来源） |

> 旧入口 `scripts/pc-config/build_fixtures.py` 已加保护：目标 `catalog.json` 存在时默认拒绝执行，必须显式 `--force` 才会覆盖，避免把运行时目录回退到旧的 3,974 条选择集。

刷新步骤：

1. 在 `data/pc-config/cleaning/stage4-price-observations.jsonl` 追加价格观测（只追加，修正用 `"overwrite": true`）。
2. 依次运行 `stage4_hot_shortlist.py` → `apply_price_observations.py` → `stage4_price_fallback.py` → `build_benchmark_image_maps.py` → `export_runtime_catalog.py`。
3. 运行 `build_offers_from_shortlist.py`，让 `offers.json` 与 catalog 同版本（`catalog_version` 必须一致，否则快照里的报价口径不可信）。
4. 重启 application-service，使启动期夹具缓存重新加载；旧快照不会被回填或迁移。
5. 已过期报价在下一次求解时自动被 `isUsableOn` 排除；某类别因此无可用报价时，求解返回 `NO_CANDIDATES`。

## 15. 【未实现】

- 报价自动过期清理或定时抓取；目前依赖人工或脚本重跑。
- 夹具版本化、回滚与变更审计；`catalog_version` 只是字符串，没有历史归档。
- 生命周期状态自动流转（如自动标记 `EOL`）与数据质量自动升级。
- 快照的保留期、归档与物理清理策略。
- `parent_build_id` 写入、方案对比与硬件替换链路。
- 治理主数据接入运行时与 `OfferRepository`。

## 16. 常见误用

- 把 `price_cny` 当运行时价格或用浮点金额；把报价当硬件（同一硬件可有多条报价，求解只取最低有效价）。
- 用 `reference_price` 判断预算或中国区价格；它明确不参与预算。
- 用 `SELECT *` 读快照；应按业务列读取，并同时带 `build_id` 与 `user_id`。
- 把 `PENDING` 写进运行时（脚本会跳过）；重复 `hardware_id` 会被 `Map` 静默覆盖，生成阶段必须保证唯一。
- 把 `market_status=UNVERIFIED` 当成 `EOL`；两者语义不同，前者是「无市场证据」。
