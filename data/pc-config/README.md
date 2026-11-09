# PC 硬件主数据产物目录

| 项 | 内容 |
| --- | --- |
| 状态 | Stage 8 生成，`catalog_version=2026.11.0` |
| 权威格式 | JSONL；Parquet 等格式只能由 JSONL 派生，不得反向覆盖 |
| 原始数据 | 外部只读目录 `F:\LLM_PC_Agent\Hardware data`，本目录不保存原始 CSV |
| 方案与规则 | [Stage 8 实施方案](../../docs/planning/Stage8.md)、[ADR 0013–0017](../../docs/adr/) |

## 1. 目录职责

| 路径 | 是否入库 | 说明 |
| --- | --- | --- |
| `manifest/catalog-manifest.json` | 是 | 当前发布批次：版本、输入 CSV 的 sha256、脚本摘要、计数与分发状态 |
| `manifest/history/<batch_id>.json` | 是 | 每次发布的追加式历史清单 |
| `manifest/baseline.json` | 是 | 原始数据基线核查结果（由 `inspect_dataset.py` 生成） |
| `manifest/classification.json` | 是 | 生命周期与推荐资格分类汇总，含每类 UNKNOWN 占比 |
| `schema/*.schema.json` | 是 | 公共字段与八类专属规格的 JSON Schema |
| `samples/<category>.sample.jsonl` | 是 | 每类 10 条真实样本，用于 CI 离线校验 |
| `master/hardware-master.jsonl` | 否 | 全量硬件主数据（含 `raw_specs` 原始行） |
| `master/hardware-benchmarks.jsonl` | 否 | PassMark 跑分映射 |
| `staging/duplicates.jsonl`、`conflicts.jsonl` | 否 | 重复与冲突的人工审核队列，只发现不合并 |
| `pools/*.jsonl` | 否 | 四类发布候选池 |
| `export/third-party-mapping-input.json` | 否 | 第三方商品映射输入，含中文检索键，回填字段留给 Stage 9 |

## 2. 许可门禁

PCPartPicker 与 PassMark 数据的再分发许可尚未核实，因此：

- `manifest.distribution_status` 固定为 `INTERNAL_ONLY`。
- `.gitignore` 忽略 `master/`、`pools/`、`export/`、`staging/` 下的全量文件。
- 版本库只提交 Schema、清单、分类汇总、样本与报告。
- 许可核实通过后，将 `distribution_status` 改为 `PUBLISHABLE` 并调整 `.gitignore`，作为独立提交。

## 3. 再生成命令

从仓库根执行，需先设置 `PC_DATA_DIR` 或传 `--data-dir`：

```powershell
python scripts/pc-config/inspect_dataset.py
python scripts/pc-config/hardware_schema.py --export-dir data/pc-config/schema
python scripts/pc-config/normalize_specs.py --full-catalog-jsonl data/pc-config/master/hardware-master.jsonl
python scripts/pc-config/deduplicate_hardware.py
python scripts/pc-config/map_benchmarks.py
python scripts/pc-config/classify_lifecycle.py
python scripts/pc-config/publish_candidates.py
```

## 4. 中文检索键

英文主数据不能直接命中中文电商标题，`export/third-party-mapping-input.json` 的每条记录都有 `search_queries`：

| 键 | 用途 | 示例 |
| --- | --- | --- |
| `zh` | 完整中文检索串 | `华硕 TUF Gaming GeForce RTX 5060 Ti 16 GB` |
| `zh_short` | 品牌 + 型号 | `华硕 RTX 5060 Ti 16GB` |
| `model` | 纯型号，防止品牌译名差异 | `RTX 5060 Ti 16GB` |
| `en` | 英文兜底 | `Asus GeForce RTX 5060 Ti 16GB` |

- 词典：`scripts/pc-config/reference/brand-zh.json`、`series-zh.json`，只做命名映射，不推断规格。
- 未登记品牌保持英文，不机器翻译；补词典即可提升覆盖率，无需改代码。
- 词典的 `schema_version` 与 `sha256` 记录在 `catalog-manifest.json.references`。

## 5. 校验与发布门禁

```powershell
python -m pytest scripts/pc-config/tests -q
python scripts/pc-config/validate_dataset.py
powershell -File scripts/pc-config/verify-release.ps1 -DataDir "F:\LLM_PC_Agent\Hardware data"
```

- `publish_candidates.py` 在写盘前调用 `validate_dataset.py` 的内存校验，任一错误即不写入任何文件。
- `--dry-run` 只校验与打印统计，用于全量验收。
- 同一输入重复执行时，`master/`、`pools/`、`export/` 的字节内容保持一致。
