# PC 硬件主数据治理报告

| 项 | 内容 |
| --- | --- |
| 适用范围 | `data/pc-config/` 离线治理批次的输入、状态分布、跑分映射、候选池与已知限制 |
| 状态 | Current（离线产物已生成，未接入运行时） |
| 最后更新 | 2026-11-17 |
| 发布批次 | `20261109T000000Z-3d66ed` |
| `catalog_version` | `2026.11.0`（离线） |
| 分发状态 | `INTERNAL_ONLY`（原始数据许可未核实） |
| 主要证据 | `data/pc-config/manifest/catalog-manifest.json`、`data/pc-config/master/*.jsonl`、`data/pc-config/pools/*.jsonl` |

## 1. 结论先行

- 离线主数据 **8,238** 条，全部保留，没有因治理删除硬件。
- 运行时目录是另一条链路：`catalog.json` 当前 **402** 款；两者尚未建立显式映射。
- 治理状态 `VALID` 6,954 / `INCOMPLETE` 1,284；生命周期 `UNKNOWN` 2,782（33.8%），集中在散热、机箱、电源。
- 跑分映射 3,557 条，`UNMATCHED` 1,610（45.3%），存储匹配率尤其低。
- 重复线索 2,203 条、冲突组 473 组，只登记审核队列，未自动合并。

## 2. 输入规模

| 数据源 | 表 | 行数 |
| --- | --- | --- |
| PCPartPicker | CPU | 493 |
| PCPartPicker | GPU | 1,109 |
| PCPartPicker | 主板 | 781 |
| PCPartPicker | 内存 | 1,891 |
| PCPartPicker | 存储 | 1,485 |
| PCPartPicker | 散热 | 863 |
| PCPartPicker | 机箱 | 1,098 |
| PCPartPicker | 电源 | 518 |
| PCPartPicker | 合计 | **8,238** |
| PassMark | CPU / GPU / DISK | 6,171 / 3,032 / 16,115 |

输入 `sha256` 记录在 `manifest/baseline.json` 与 `catalog-manifest.json.inputs`；原始 CSV 不进入仓库。

## 3. 状态分布

| 字段 | 分布 |
| --- | --- |
| `data_quality_status` | `VERIFIED_STRUCTURED` 6,954 / `PARTIAL` 1,071 / `BLOCKED` 213 |
| `governance_status` | `VALID` 6,954 / `INCOMPLETE` 1,284 / `INVALID` 0 / `CONFLICT` 0 |
| `lifecycle_status` | `CURRENT` 1,798 / `MATURE` 2,319 / `LEGACY` 1,197 / `DISCONTINUED` 142 / `UNKNOWN` 2,782 |
| `market_status` | `UNVERIFIED` 8,238 |
| `recommendation_status` | `ELIGIBLE` 7,263 / `RESTRICTED` 833 / `EXCLUDED` 142 |

五个状态字段互相独立：新增 `governance_status` 不改写 `data_quality_status`，避免破坏运行时读取逻辑。

## 4. 生命周期分类

规则见 `scripts/pc-config/reference/platform-generations.json`，`rule_version=1.0.0`，人工覆盖 0 条。

| 类别 | CURRENT | MATURE | LEGACY | DISCONTINUED | UNKNOWN |
| --- | --- | --- | --- | --- | --- |
| CPU | 57 | 73 | 265 | 86 | 12 |
| GPU | 305 | 259 | 335 | 0 | 210 |
| 主板 | 458 | 226 | 79 | 13 | 5 |
| 内存 | 883 | 584 | 381 | 43 | 0 |
| 存储 | 95 | 1,177 | 137 | 0 | 76 |
| 散热 | 0 | 0 | 0 | 0 | 863 |
| 机箱 | 0 | 0 | 0 | 0 | 1,098 |
| 电源 | 0 | 0 | 0 | 0 | 518 |

- CPU 按 Socket 代际、GPU 按 Chipset 正则、主板按 Socket + Chipset、内存按 DDR、存储按接口。
- 散热、机箱、电源缺少可靠发布日期或平台绑定，统一 `UNKNOWN`，属于预期结果。
- `UNKNOWN` 不等于 `EXCLUDED`；推荐资格由类别规则独立派生。

## 5. 兼容性关键字段缺失

| 类别 | 字段 | 条数 | 处理 |
| --- | --- | --- | --- |
| GPU | `length_mm` | 24 | `governance_status=INCOMPLETE`，`RESTRICTED` |
| 机箱 | `supported_mainboard_form_factors` | 1 | `INCOMPLETE`，`RESTRICTED` |

缺失值保持 `null`，不猜测填充。运行时 402 款目录另有 20 款机箱缺 `max_cooler_height_mm`、11 款散热缺 `height_mm`，导致兼容性常为 `UNKNOWN`，见 [data.md](../pc-config/data.md) §3。

## 6. 重复与冲突

| 线索 | 组数 |
| --- | --- |
| `MPN` | 3 |
| `BRAND_MODEL` | 1,148 |
| `MODEL_SIGNATURE` | 1,052 |
| 合计（同一记录可命中多条） | 2,203 |
| 冲突组 | 473 |

冲突记录保留在主数据并标记待复核，不删除、不覆盖；审核队列在 `data/pc-config/staging/`。

## 7. PassMark 映射

| 指标 | 输入 | 已匹配 | 未匹配 | 歧义 | 匹配率 |
| --- | --- | --- | --- | --- | --- |
| CPU `CPUMARK` | 493 | 470 | 23 | 0 | 95.3% |
| CPU `SINGLE_THREAD` | 493 | 470 | 23 | 0 | 95.3% |
| GPU `G3D_MARK` | 1,109 | 992 | 117 | 0 | 89.5% |
| 存储 `DISK_MARK` | 1,485 | 10 | 1,470 | 5 | 0.67% |

- GPU 板卡级记录映射到芯片级（`match_scope=CHIPSET`），多对一。
- 存储匹配率低是数据源限制：PassMark DISK 大量记录名为 `harddisk SSD` 等通用名。
- 未匹配记录保留 `score=null`，不猜测分数。
- 全部映射 3,557 行：`MATCHED` 1,942 / `UNMATCHED` 1,610 / `AMBIGUOUS` 5。

## 8. 发布候选池

| 候选池 | 条数 | 准入规则 |
| --- | --- | --- |
| `standard-build` | 4,107 | `ELIGIBLE` 且生命周期 `CURRENT` / `MATURE` |
| `budget-build` | 7,200 | 非归档；性能类需有可用跑分；不读取价格 |
| `legacy-upgrade` | 1,197 | `LEGACY` 且可推荐 |
| `archived` | 142 | `DISCONTINUED` 或治理 `INVALID` |

`archived` 与前三类互斥；池内条目携带 `catalog_version`、`pool_version`、`rule_version` 与关键规格。

## 9. 第三方映射输入

- 输出 8,096 条，等于非 `EXCLUDED` / `ARCHIVED` 硬件。
- 字段含 `hardware_id`、`category`、`brand`、`model_name`、`manufacturer_part_number`、`aliases`、`search_queries`、`key_specs`、状态字段与 `catalog_version`。
- `matched_mpn`、`matched_specs`、`source`、`fetched_at` 为 `null`，`match_status=PENDING`。
- 中文检索键按 `zh` / `zh_short` / `model` / `en` 四级降级；品牌与系列只走受控词典，未登记品牌保留英文原名。
- 多数记录可生成中文 `zh` 键，其余走英文兜底；具体条数以当期导出产物为准。

## 10. 质量门禁与幂等

- `validate_dataset.py` 校验 Schema、必填、枚举、兼容字段、重复 ID、跑分关联、池准入复算、导出契约与清单一致性。
- `publish_candidates.py` 写盘前执行同一套内存校验，失败不覆盖上一批次。
- 连续两次完整流水线产物的 `sha256` 一致。
- 原始 CSV 零写入；输入哈希与基线一致。
- 运行时 402 款目录的 `hardware_id` 与治理主数据保持同一规则。

## 11. 已知限制

- 离线治理产物未接入 Java 运行时；运行时仍读 classpath 夹具。
- 运行时目录 402 款与离线主数据 8,238 条无显式筛选清单，无法从线上配置反查治理批次。
- 存储跑分覆盖不足，不能用于存储性能排序。
- 散热、机箱、电源的生命周期保持 `UNKNOWN`。
- 原始数据许可未核实，`distribution_status` 维持 `INTERNAL_ONLY`。
- 报价全部为平台观测价，无人工核验价，见 [market-offer-management.md](../pc-config/market-offer-management.md)。

## 12. 相关文档

- 数据与运行时分册：[data.md](../pc-config/data.md)
- 报价管理：[market-offer-management.md](../pc-config/market-offer-management.md)
- 路线图：[roadmap.md](../planning/roadmap.md)
