# PC 硬件主数据治理报告（Stage 8）

| 项 | 内容 |
| --- | --- |
| 状态 | 已生成，等待评审 |
| 生成日期 | 2026-11-09 |
| 发布批次 | `20261109T000000Z-3d66ed` |
| catalog_version | `2026.11.0` |
| 分发状态 | `INTERNAL_ONLY`（原始数据许可未核实） |
| 产物位置 | `data/pc-config/`（全量明细本地生成，Schema/清单/样本入库） |
| 方案依据 | [roadmap](../planning/roadmap.md) §4、[PC 配置模块决策合并记录](../adr/0027-pc-config-decisions.md) §3 |
| 校验命令 | `python scripts/pc-config/validate_dataset.py`、`python -m pytest scripts/pc-config/tests -q` |

## 1. 输入规模

原始数据来自只读目录，未做任何删除或覆盖。

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
| PassMark | CPU | 6,171 |
| PassMark | GPU | 3,032 |
| PassMark | DISK | 16,115 |
| PassMark | 合计 | **25,318** |

输入文件的 `sha256` 记录在 `data/pc-config/manifest/baseline.json`，并写入 `catalog-manifest.json.inputs`。

## 2. 治理结果概览

8,238 条原始记录全部保留，没有因治理而删除硬件。

| 环节 | 数量 | 说明 |
| --- | --- | --- |
| 原始记录 | 8,238 | PCPartPicker 八类合计 |
| 清洗后 | 8,238 | 零删除；异常与缺失通过状态字段表达 |
| 无效（`INVALID`） | 0 | 没有无法解析到类别的记录 |
| 冲突待复核 | 473 组 | 保留在主数据，仅进入审核队列 |

| 状态字段 | 取值分布 |
| --- | --- |
| `data_quality_status` | `VERIFIED_STRUCTURED` 6,954 / `PARTIAL` 1,071 / `BLOCKED` 213 |
| `governance_status` | `VALID` 6,954 / `INCOMPLETE` 1,284 / `INVALID` 0 / `CONFLICT` 0 |
| `lifecycle_status` | `CURRENT` 1,798 / `MATURE` 2,319 / `LEGACY` 1,197 / `DISCONTINUED` 142 / `UNKNOWN` 2,782 |
| `market_status` | `UNVERIFIED` 8,238 |
| `recommendation_status` | `ELIGIBLE` 7,263 / `RESTRICTED` 833 / `EXCLUDED` 142 |

## 3. 生命周期分类

规则见 `scripts/pc-config/reference/platform-generations.json`，`rule_version=1.0.0`，人工覆盖 0 条。

| 类别 | CURRENT | MATURE | LEGACY | DISCONTINUED | UNKNOWN | UNKNOWN 占比 |
| --- | --- | --- | --- | --- | --- | --- |
| CPU | 57 | 73 | 265 | 86 | 12 | 2.43% |
| GPU | 305 | 259 | 335 | 0 | 210 | 18.94% |
| 主板 | 458 | 226 | 79 | 13 | 5 | 0.64% |
| 内存 | 883 | 584 | 381 | 43 | 0 | 0.00% |
| 存储 | 95 | 1,177 | 137 | 0 | 76 | 5.12% |
| 散热 | 0 | 0 | 0 | 0 | 863 | 100.00% |
| 机箱 | 0 | 0 | 0 | 0 | 1,098 | 100.00% |
| 电源 | 0 | 0 | 0 | 0 | 518 | 100.00% |

判定口径：

- CPU 按 Socket 代际表，GPU 按 Chipset 正则；两者都不使用 LLM 记忆补全。
- 主板按 Socket + Chipset，内存按 DDR 代际，存储按接口代际。
- 散热、机箱、电源的原始数据没有可靠发布日期或平台绑定，统一 `UNKNOWN`，这是预期结果而非缺陷。
- `UNKNOWN` 不等于 `EXCLUDED`：推荐资格由类别独立规则决定。

## 4. 缺失的兼容性关键字段

| 类别 | 字段 | 条数 | 处理 |
| --- | --- | --- | --- |
| GPU | `length_mm` | 24 | `governance_status=INCOMPLETE`，推荐资格 `RESTRICTED` |
| 机箱 | `supported_mainboard_form_factors` | 1 | `INCOMPLETE`，`RESTRICTED` |

其余类别的兼容性关键字段在本次数据中均无缺失。缺失值一律保持 `null`，未做任何猜测填充。

## 5. 重复与冲突

只发现、不合并；审核队列位于 `data/pc-config/staging/`。

| 线索 | 组数 | 说明 |
| --- | --- | --- |
| `MPN` | 3 | 同厂同料号 |
| `BRAND_MODEL` | 1,148 | 同品牌同型号 |
| `MODEL_SIGNATURE` | 1,052 | 去品牌、去描述词后的型号签名 |
| 合计 | 2,203 | 同一记录可能命中多条线索 |
| 冲突组 | 473 | 同线索但兼容性关键字段不一致 |

冲突记录全部保留在主数据中并标记为待复核，不删除、不覆盖。

## 6. PassMark 映射

| 指标 | 输入 | 已匹配 | 未匹配 | 歧义 | 匹配率 |
| --- | --- | --- | --- | --- | --- |
| CPU `CPUMARK` | 493 | 470 | 23 | 0 | 95.3% |
| CPU `SINGLE_THREAD` | 493 | 470 | 23 | 0 | 95.3% |
| GPU `G3D_MARK` | 1,109 | 992 | 117 | 0 | 89.5% |
| 存储 `DISK_MARK` | 1,485 | 10 | 1,470 | 5 | 0.67% |

- GPU 为板卡级记录映射到芯片级跑分（`match_scope=CHIPSET`），1,109 张卡对应 242 个 chipset，采用多对一。
- 存储匹配率极低是数据源限制：PassMark DISK 表大量记录名称为 `harddisk SSD` 等通用名，缺少可比型号。
- 未匹配记录保留 `score=null` 与 `match_status=UNMATCHED`，不猜测分数。
- 全部映射记录共 3,557 行：`MATCHED` 1,942、`UNMATCHED` 1,610、`AMBIGUOUS` 5。

## 7. 发布候选池

| 候选池 | 条数 | 准入规则 |
| --- | --- | --- |
| `standard-build` | 4,107 | `recommendation_status=ELIGIBLE` 且生命周期为 `CURRENT`/`MATURE` |
| `budget-build` | 7,200 | 非归档；性能类必须有可用跑分，非性能类不要求跑分；**不读取价格** |
| `legacy-upgrade` | 1,197 | 生命周期 `LEGACY` 且可推荐 |
| `archived` | 142 | 生命周期 `DISCONTINUED` 或治理 `INVALID` |

`archived` 与前三类互斥；同一硬件不重复进入同一池。池内条目携带 `catalog_version`、`pool_version`、`rule_version` 与关键规格。

## 8. 第三方映射输入

- 输出 8,096 条，等于全部非 `EXCLUDED`/`ARCHIVED` 硬件。
- 字段包含 `hardware_id`、`category`、`brand`、`model_name`、`manufacturer_part_number`、`aliases`、`search_queries`、`key_specs`、状态字段与 `catalog_version`。
- `matched_mpn`、`matched_specs`、`source`、`fetched_at` 固定为 `null`，`match_status=PENDING`，等待 Stage 9 接入真实商品源后回填。
- 不包含 `raw_specs`，避免把原始行扩散到外部系统。

### 8.1 中文检索键

英文主数据无法直接命中中文电商标题，因此每条导出记录附带四级检索键，调用方按顺序降级：

```json
"search_queries": {
  "zh": "华硕 TUF Gaming GeForce RTX 5060 Ti 16 GB",
  "zh_short": "华硕 RTX 5060 Ti 16GB",
  "model": "RTX 5060 Ti 16GB",
  "en": "Asus GeForce RTX 5060 Ti 16GB"
}
```

生成规则：

- 品牌与系列只走受控词典（`scripts/pc-config/reference/brand-zh.json`、`series-zh.json`），共登记 79 个品牌与 6 条 CPU 系列规则。
- 型号数字与字母保持原文；`GeForce`/`Radeon` 仅在 `zh_short` 中省略，因为中文电商标题普遍直接用 `RTX 5060 Ti` 这类写法。
- 未登记品牌不机器翻译，直接沿用英文原名，并保证 `en` 键保留原始型号。
- 该映射只做命名转换，不推断任何规格，与 [PC 配置模块决策合并记录](../adr/0027-pc-config-decisions.md) §3.3 的「不猜测」一致。

品牌覆盖：8,096 条导出记录中 7,163 条（88.5%）生成了含中文的 `zh` 键。

| 类别 | 含中文 `zh` | 导出总数 | 覆盖率 |
| --- | --- | --- | --- |
| CPU | 389 | 407 | 95.6% |
| GPU | 1,017 | 1,109 | 91.7% |
| 主板 | 752 | 768 | 97.9% |
| 内存 | 1,787 | 1,848 | 96.7% |
| 存储 | 1,315 | 1,485 | 88.6% |
| 散热 | 664 | 863 | 76.9% |
| 机箱 | 819 | 1,098 | 74.6% |
| 电源 | 420 | 518 | 81.1% |

剩余 933 条走英文兜底，集中在机箱、散热与存储的小众品牌；补充词典即可提升，不需要改代码。

## 9. 质量门禁与幂等

- `validate_dataset.py` 校验 Schema、必填、枚举、兼容性关键字段、重复 ID、跑分关联、池准入复算、导出契约与清单一致性，本次 0 错误。
- `publish_candidates.py` 在写盘前执行同一套内存校验，失败时不覆盖上一批次产物。
- 幂等实测：连续两次执行完整流水线，`hardware-master.jsonl`、`hardware-benchmarks.jsonl`、`third-party-mapping-input.json` 与 `catalog-manifest.json` 的 `sha256` 完全一致。
- 原始数据零写入：11 个输入 CSV 的 `sha256` 与 `manifest/baseline.json` 记录逐项一致，未做任何修改。
- 现有 28 条 classpath 夹具的 `hardware_id` 100% 可复现，`tests/test_id_stability.py` 守护该契约。
- `scripts/pc-config/tests` 共 99 项测试全部通过；CI 新增 `data` 任务运行 pytest 与入库样本 Schema 校验，全量数据由 `verify-release.ps1` 在本地验收。

## 10. 已知限制与 Stage 9 前置条件

- 在线推荐覆盖率本期不提升：`BuildSolver` 只接受有可用 offer 的硬件，候选池扩容需等 Stage 9 接入真实报价后才生效（[PC 配置模块决策合并记录](../adr/0027-pc-config-decisions.md) §3.5）。
- PassMark 存储跑分覆盖不足，不能用于存储性能排序；需要更可靠的存储跑分源。
- 散热、机箱、电源的生命周期无法从现有数据判定，保持 `UNKNOWN`。
- 原始数据许可未核实，`distribution_status` 维持 `INTERNAL_ONLY`。
- 机箱缺少 `max_cooler_height_mm`，散热兼容性仍按既有规则处理。
