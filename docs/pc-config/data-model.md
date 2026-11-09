# PC 配置数据模型

| 项 | 内容 |
| --- | --- |
| 状态 | 已验证（对照 2026-11-08 分支源码与夹具） |
| 最后核验 | 2026-11-08 |
| 权威性 | 本文件描述三份 classpath 夹具与 `pc_build_snapshots` 的结构；HTTP 字段以 [api-contract.md](../api-contract.md) §5.7 为准，术语见 [glossary.md](./glossary.md) |
| 主要证据 | `application-service/src/main/resources/pc-config/*.json`、`application-service/.../pcbuild/domain/*.java`、`V24__create_pc_build_snapshots.sql`、`scripts/pc-config/` |

## 1. 三份夹具与加载

| 文件 | 读取方 | 内容 |
| --- | --- | --- |
| `pc-config/catalog.json` | `JsonHardwareCatalogRepository` | 硬件、规格、数据质量状态与 `catalog_version` |
| `pc-config/benchmarks.json` | `JsonBenchmarkRepository` | CPU / GPU 的 PassMark 跑分 |
| `pc-config/offers.json` | `JsonOfferRepository` | 中国区商品报价与整体 `data_status` |

三者由 `JsonFixtureLoader` 在启动期读入并缓存；文件缺失抛 `40305 CATALOG_UNAVAILABLE`，解析失败阻止启动。修改夹具后必须重启 Java，热加载与运行时刷新接口【未实现】。

## 2. `catalog.json` 顶层

| 键 | 类型 / 示例 | 用途 |
| --- | --- | --- |
| `schema_version` / `generated_at` | `"1.0.0"` / ISO-8601 | 夹具结构版本与生成时刻，不参与求解 |
| `catalog_version` | `"2026-11-08-demo-1"` | 随快照落库，用于判断历史方案可比性 |
| `source` / `platform_pairs` | 来源对象 / 平台对照数组 | 原始来源与行数（当前 `raw_rows=28`）；`platform` 对应 `cpu_socket` 与 `memory_type` |
| `hardware` | 对象数组 | 28 条硬件，见 §3 |

## 3. `hardware[]` 条目

| 字段 | 说明 |
| --- | --- |
| `hardware_id` | 稳定主键，报价与跑分通过它关联 |
| `category` | `CPU` / `MOTHERBOARD` / `MEMORY` / `GPU` / `PSU` / `CASE` / `COOLER` / `STORAGE` |
| `brand` / `model_name` / `display_name` | 品牌、标准型号、展示名 |
| `specifications` | 扁平规格对象，缺失值为 `null`，见 §4 |
| `source` | 含 `dataset`、`pcpp_id`、`source_url`、`image_url`、`reference_price`、`reference_price_note`；参考价不参与预算 |
| 状态三字段 | `data_quality_status`（`VERIFIED_STRUCTURED` / `PARTIAL`）、`lifecycle_status`（当前 `CURRENT`）、`recommendation_status`（当前 `ELIGIBLE`）；后两者决定是否进入候选池 |
| `unverified_fields` | 未核验字段名数组；当前 3 款机箱均为 `["max_cooler_height_mm"]` |
| `selection_reason` | 入选理由，仅展示 |

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

顶层为 `schema_version`、`generated_at`、`source{name,snapshot_date}`、`entries`、`unmatched`。条目字段：`hardware_id`、`benchmark_type`（CPU 为 `CPUMARK`，GPU 为 `G3D_MARK`）、`score`（小数）、`secondary_score`、`rank_no`、`samples`、`source{name,source_id,source_name,snapshot_date}`、`match_method`、`match_confidence`。当前 8 条，仅覆盖 CPU / GPU。

## 6. `offers.json`

顶层：`schema_version`、`generated_at`、`data_status`、`currency`（`CNY`）、`price_unit`（`CNY_FEN`）、`catalog_version`、`offers`、`verified_offer_count`、`mock_offer_count`、`skipped_pending`。条目字段：`offer_id`、`hardware_id`、`category`、`platform`、`seller`、`shop_name`、`title`、`platform_sku`、`price_fen`、`price_type`、`purchase_url`、`verified_at`、`valid_until`、`match_status`、`price_source`、`notes`。

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
| `compatibility_report` | `jsonb` NOT NULL | 八条规则结论与 `ruleVersion` |
| `benchmark_snapshot` / `offer_snapshot` | `jsonb` NOT NULL | 选用跑分与报价（含 `data_status`） |
| `solver_version` / `compatibility_rule_version` | `varchar(32)` | 求解器与规则版本 |
| `catalog_version` / `created_at` | `varchar(64)` / `timestamptz` | 目录版本与创建时间 |

索引为 `(user_id, created_at DESC)` 与 `(parent_build_id)`。表为 append-only：只插入，不更新、不删除。

## 9. 更新入口

| 数据 | 入口 |
| --- | --- |
| catalog / benchmarks | `scripts/pc-config/build_fixtures.py`（`normalize_specs.py`、`match_benchmarks.py`）→ `application-service/src/main/resources/pc-config/` |
| offers | 人工填写 [offers.template.json](./offers.template.json) → `scripts/pc-config/ingest_offers.py` → 同一 resources 目录 |
| 候选范围 | [candidate-shortlist.md](./candidate-shortlist.md) 与 `scripts/pc-config/candidate_selection.json` |

`build_fixtures.py` 在 `offers.json` 已存在时不覆盖，避免冲掉人工报价。

## 10. 常见误用

- 把 `price_cny` 当运行时价格或用浮点金额；把报价当硬件（报价是平台在售记录，同一硬件可有多条，求解只取最低有效价）。
- 用 `reference_price` 判断预算或中国区价格；它明确不参与预算。
- 用 `SELECT *` 读快照；应按业务列读取，并同时带 `build_id` 与 `user_id`。
- 把 `PENDING` 写进运行时（脚本会跳过）；重复 `hardware_id` 会被 `Map` 静默覆盖，生成阶段必须保证唯一。

## 11. 治理产物 `data/pc-config/`（Stage 8）

| 路径 | 权威性 | 说明 |
| --- | --- | --- |
| `master/hardware-master.jsonl` | 全量主数据（本地生成） | 8 类硬件，含 `raw_specs` 原始行与五个状态字段；JSONL 是权威格式 |
| `master/hardware-benchmarks.jsonl` | 全量跑分映射（本地生成） | PassMark 映射，含 `match_method`、`match_confidence`、`match_scope` |
| `schema/*.schema.json` | 入库 | 公共字段与八类专属规格的 JSON Schema |
| `manifest/catalog-manifest.json` | 入库 | 发布批次、输入 `sha256`、脚本摘要、计数与分发状态 |
| `pools/*.jsonl` | 派生（本地生成） | 四类发布候选池，由主数据与跑分派生 |
| `export/third-party-mapping-input.json` | 派生（本地生成） | 第三方商品映射输入，回填字段为 `null` |

关系约束：

- 治理产物与 classpath 夹具**互不替换**：`catalog.json` 仍是运行时唯一入口，`data/pc-config/` 只服务离线治理与 Stage 9 接入准备。
- `hardware_id` 规则与 `catalog.json` 完全一致；8,238 条主数据中仅 2,094 条因重名追加 `-<source_id>` 后缀，现有 28 条 ID 不受影响。
- 原始 CSV 不进入仓库；`manifest.inputs` 用 `sha256` 标识输入版本。
- 金额仍以 Java 侧 `long` 分为准，治理产物不提供 `price_cny_fen`，报价沿用 [market-offer-management.md](./market-offer-management.md)。
- 字段级细节与产物目录说明见 `data/pc-config/README.md`，实测数据见 [硬件主数据治理报告](../quality/hardware-data-governance-report.md)。
