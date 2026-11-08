# Stage 8 实施方案（v2 修订版）：PC 硬件主数据治理与推荐候选池

| 项 | 内容 |
| --- | --- |
| 版本 | v2，2026-11-09 修订 |
| 状态 | 已决策，待执行 |
| 修订依据 | Q1–Q6 六项决策（数据产物位置、运行时边界、状态字段、生命周期、ETL 归属、Git 基线） |
| 权威性 | 本文件是 Stage 8 的唯一实施口径；与 [candidate-shortlist.md](../pc-config/candidate-shortlist.md) 冲突时以本文件为准 |
| 事实基线 | `F:\LLM_PC_Agent\Hardware data`（只读）、`scripts/pc-config/`、`application-service/.../pcbuild/`、[data-model.md](../pc-config/data-model.md) |

## 0. 修订要点（相对 v1）

1. 治理产物落在仓库内 `data/pc-config/`，**JSONL 为权威**，Parquet 仅作派生格式；原始数据保持外部只读。
2. 本期**不接入 Java 运行时**，不改 Repository / Solver / Agent / 前端；交付价值是标准化硬件资产，不是在线覆盖率。
3. 现有 `data_quality_status` 语义保持不变，治理结论写入**新字段 `governance_status`**。
4. 生命周期**分类别分阶段**推进；`lifecycle_status=UNKNOWN` 不等于 `recommendation_status=EXCLUDED`。
5. ETL **原地演进** `scripts/pc-config/`，禁止第二套流水线；脚本测试纳入 CI 门禁。
6. 开工前完成受控 Git 基线（复核 → 分组提交 → 建 Stage 8 分支）。

## 1. 目标与边界

### 1.1 本期目标

把 8,238 条 PCPartPicker 原始硬件与 25,318 条 PassMark 跑分加工为可追溯、可分级、可重复生成的硬件主数据，并输出候选池与第三方商品映射输入清单。

### 1.2 明确不做

- 不改 `application-service` 的 `pcbuild` 任何类、接口、迁移与 `catalog.json`；不调整 `PcFixtureRepositoryTests` 的数据规模与断言。
- 不改 `agent-service` 工作流、SSE、提示词与前端 `BuildResultCard`。
- 不实现电商采集、第三方商品服务客户端、自动比价。
- 不把价格与购买链接写入硬件主数据（属于 Marketplace Offer 领域）。
- 不因数据治理而重构 BuildSolver 或兼容性规则。
- 不承诺在线推荐覆盖率提升；该评估只在 Stage 9 完成后进行。

### 1.3 与 Stage 9 的接口承诺

Stage 8 必须保证：`hardware_id` 稳定、主数据可被 `hardware_id` 回关联、第三方输入清单字段完整。Stage 9 负责导入第三方商品、建立 `hardware_id` ↔ 报价映射并接入 `OfferRepository`。

## 2. 状态字段口径（五个字段相互独立）

| 字段 | 语义 | 取值 | 消费者 | 是否本期新增 |
| --- | --- | --- | --- | --- |
| `data_quality_status` | 结构化字段完整度（现有语义，不改） | `VERIFIED_STRUCTURED` / `PARTIAL` | 现有 Java 夹具、前端披露 | 否，保持原样 |
| `governance_status` | 本次数据治理结论 | `VALID` / `INCOMPLETE` / `INVALID` / `CONFLICT` | 候选池发布、质量报告 | **是** |
| `lifecycle_status` | 产品生命周期 | `CURRENT` / `MATURE` / `LEGACY` / `DISCONTINUED` / `UNKNOWN` | 候选池规则 | 是（Java 现有代码只识别 `DISCONTINUED`/`EOL`，新增值不影响在线链路） |
| `market_status` | 市场可得性 | `AVAILABLE` / `UNAVAILABLE` / `UNVERIFIED` | 候选池规则、质量报告 | 是 |
| `recommendation_status` | 推荐资格 | `ELIGIBLE` / `RESTRICTED` / `EXCLUDED` / `ARCHIVED` | 候选池规则；Stage 9 之后的 Java 候选过滤 | 取值扩展 |

约束：

- 任一字段不得替代另一字段；`governance_status=VALID` 不推导出 `recommendation_status=ELIGIBLE`。
- `CURRENT` 不等于 `ELIGIBLE`，`LEGACY` 不等于 `EXCLUDED`（由 §6 规则表决定）。
- 未采集任何市场信息的记录，`market_status=UNVERIFIED`，不得写 `AVAILABLE`。

## 3. 数据产物目录（Q1）

```
data/pc-config/
├── README.md                       目录说明、许可声明、再生成命令
├── manifest/
│   ├── catalog-manifest.json       当前发布的版本、批次、输入摘要、脚本版本、许可状态
│   └── history/<batch_id>.json     每次发布的历史清单（append-only）
├── schema/
│   ├── hardware-master.schema.json 公共字段 + 类别判别
│   └── <category>.schema.json      八类专属规格 Schema
├── master/
│   ├── hardware-master.jsonl       权威：全量硬件主数据（含 raw_specs 原始规格）
│   └── hardware-benchmarks.jsonl   权威：跑分映射
├── staging/
│   ├── duplicates.jsonl            重复候选（保留全部原始行）
│   └── conflicts.jsonl             冲突记录，进入人工审核队列
├── pools/
│   ├── standard-build-pool.jsonl
│   ├── budget-build-pool.jsonl
│   ├── legacy-upgrade-pool.jsonl
│   └── archived-pool.jsonl
├── export/
│   └── third-party-mapping-input.json
└── samples/
    └── <category>.sample.jsonl     每类固定样本（许可未确认时进入版本库的最小数据）
```

### 3.1 许可门禁

- `manifest.distribution_status` 取值 `PUBLISHABLE` / `INTERNAL_ONLY`，默认 `INTERNAL_ONLY`。
- PCPartPicker 与 PassMark 数据的使用与再分发许可未核实前：`.gitignore` 忽略 `data/pc-config/master/`、`data/pc-config/pools/`、`data/pc-config/export/`、`data/pc-config/staging/` 下的全量文件；版本库只提交 `README.md`、`manifest/`、`schema/`、`samples/`、脚本与报告。
- 许可核实通过后，将 `distribution_status` 改为 `PUBLISHABLE` 并调整 `.gitignore`，作为独立提交。

### 3.2 版本与批次

`catalog-manifest.json` 必填：`catalog_version`、`batch_id`（`<yyyyMMddTHHmmssZ>-<6位输入摘要>`）、`generated_at`、`inputs[]`（每份源 CSV 的路径、行数、sha256）、`scripts[]`（脚本名与 sha256）、`counts`（八类 + 跑分）、`distribution_status`。

## 4. 任务拆分

### Stage 8.1 基线核查（产物 `docs/quality/hardware-data-baseline.md`）

- 新增 `scripts/pc-config/inspect_dataset.py`：扫描 `PC_DATA_DIR`，输出文件清单、行数、八类分布、字段结构、缺失率、重复情况、格式异常、PassMark 关联粗测、已知异常；`--json` 输出到 `data/pc-config/manifest/baseline-<batch>.json`。
- 不动原始数据，不写 `master/`。
- 验收：报告中的每个数字都能由脚本复现；与本文 §0 的事实基线一致。

### Stage 8.2 统一 Hardware Schema（产物 `hardware_schema.py` + `data/pc-config/schema/`）

- 新增 `scripts/pc-config/hardware_schema.py`：八个类别专属的 dataclass/TypedDict 定义 + 必填/可选字段 + 单位 + 枚举 + 缺失/异常语义，并导出 JSON Schema。
- 公共字段：`hardware_id`、`source_id`、`source`、`category`、`brand`、`model_name`、`manufacturer_part_number`、`aliases`、`specifications`、`raw_specs`、四个状态字段 + `governance_status`、`source_version`、`collected_at`、`updated_at`。
- `raw_specs` 保存原始行键值，不得丢弃或改写。
- 类别专属字段见 [data-model.md](../pc-config/data-model.md) §4 的现有键，新增字段必须在此登记。

### Stage 8.3 字段规范化（产物 `master/hardware-master.jsonl`）

- 复用 [pc_config_data.py](../../scripts/pc-config/pc_config_data.py) 的解析器与 [normalize_specs.py](../../scripts/pc-config/normalize_specs.py) 的 `NORMALIZERS`，新增 `normalize_full_catalog()`；**不新建第二套解析逻辑**。
- 覆盖：Socket、Chipset、DDR 类型、板型、显卡长度/厚度、散热器高度/冷排、机箱限高限长、PSU 额定功率与供电接口、M.2/SATA、存储类型与容量、内存频率与容量、功耗与单位。
- 内存 DDR 类型无独立字段，必须从 `speed` 派生并标记 `derived=true`。
- 缺失写 `null` 并记录 `missing_reason`；**禁止推测值补全兼容性关键字段**。

### Stage 8.4 重复与实体治理（产物 `staging/duplicates.jsonl`、`staging/conflicts.jsonl`）

- 新增 `scripts/pc-config/deduplicate_hardware.py`：来源 ID 重复、MPN 重复、品牌+型号重复、别名识别、相似型号候选发现。
- 区分芯片型号 / 具体硬件型号 / 厂商 Part Number / 平台 SKU；GPU 不同厂商板卡保留各自规格，**不得按 chipset 合并**。
- 冲突一律进 `conflicts.jsonl` 人工审核，不自动合并。
- `hardware_id` 稳定规则（兼容红线）：延续现有 `build_hardware_id(category, model_name)`；新增 golden 测试，断言现有 28 条 `hardware_id` 不变。任何未来迁移必须提供别名映射，不在本期进行。

### Stage 8.5 PassMark 映射（产物 `master/hardware-benchmarks.jsonl`）

- 新增 `scripts/pc-config/map_benchmarks.py`，内部复用 `match_benchmarks.py` 的 `match_cpu` / `match_gpu`，扩展为全量映射与报告。
- 字段：`hardware_id`、`benchmark_type`（`CPUMARK` / `SINGLE_THREAD` / `G3D_MARK` / `DISK_MARK`）、`score`、`secondary_score`、`rank_no`、`samples`、`source`、`match_method`、`match_confidence`、`match_scope`、`source_name`、`collected_at`。
- **GPU 是芯片级多对一**：`match_scope=CHIPSET`，同时记录 `board_variant_count`；禁止把芯片级分数表述为单卡实测分。
- 存储匹配按型号+容量，置信度低于阈值一律 `UNMATCHED` 保留记录，不删除硬件。
- 未匹配记录写 `match_status=UNMATCHED`，计入报告。

### Stage 8.6 生命周期与推荐资格（产物写入 master + `reference/platform-generations.json`）

- 新增 `scripts/pc-config/classify_lifecycle.py` 与人工维护的 `scripts/pc-config/reference/platform-generations.json`（socket/chipset/DDR/接口 → 代际与年份区间，附来源说明）。
- 规则见 §6；`lifecycle_status` 与 `recommendation_status` 分别计算，保留 `reason` 与 `rule_version`。
- 人工覆盖：`reference/manual-overrides.json` 支持逐条覆盖，覆盖项必须在报告计数。

### Stage 8.7 候选池（产物 `pools/*.jsonl`）

- 新增 `scripts/pc-config/publish_candidates.py`：按 §6 规则生成四类池，池内记录含 `pool_id`、`catalog_version`、`pool_version`、`rule_version`、`reason`。
- 发布前执行 §8.9 的全部校验，任一失败不产出池文件。
- 池规则不得依赖价格（主数据无价格），预算池按性能档位与规格定义。

### Stage 8.8 第三方映射输入（产物 `export/third-party-mapping-input.json`）

- 同一脚本 `--export-third-party` 输出：`catalog_version`、`hardware_id`、`category`、`brand`、`model_name`、`manufacturer_part_number`、`aliases`、`key_specs`、`lifecycle_status`、`recommendation_status`。
- 预留回填校验字段：`matched_mpn`、`matched_specs`、`source`、`fetched_at`、`match_status`（本阶段只定义，不填充）。
- 明示一对多：一个硬件可对应多平台多商家商品。

### Stage 8.9 质量报告与发布（产物 `docs/quality/hardware-data-governance-report.md`）

- 新增 `scripts/pc-config/validate_dataset.py`：Schema 校验、必填字段、兼容性关键字段、重复、跑分关联、状态合法性、候选池准入、交叉引用。
- 发布门禁：三处校验全绿才写 `manifest/catalog-manifest.json`，并追加 `manifest/history/<batch_id>.json`。
- 幂等：同一输入重复执行，`master/`、`pools/`、`export/` 的 sha256 必须完全一致。

## 5. 字段兼容方案

| 现有 `catalog.json` 字段 | 新主数据字段 | 处理 |
| --- | --- | --- |
| `hardware_id` | `hardware_id` | 同一生成规则，golden 测试锁定 28 条 |
| `category` | `category` | 不变 |
| `brand` / `model_name` / `display_name` | `brand` / `model_name` / `aliases` | `display_name` 归入 `aliases` |
| `specifications` | `specifications` | 键名保持一致，新增键只增不改 |
| `source{dataset,pcpp_id,...}` | `source` + `source_id` + `source_version` | 拆分为标准字段，原始对象保留 |
| 无 | `raw_specs` | 新增，保存原始行 |
| `data_quality_status` | 同名 | 原值保留，语义不变 |
| 无 | `governance_status` | 新增 |
| `lifecycle_status` / `recommendation_status` | 同名 | 取值扩展，旧值仍合法 |
| 无 | `market_status` | 新增，默认 `UNVERIFIED` |
| `unverified_fields` | `unverified_fields` | 保留 |
| `selection_reason` | `selection_reason` | 保留，人工选品理由 |

红线：禁止把 `data_quality_status` 的取值改写成 `governance_status` 的枚举，反之亦然。

## 6. 生命周期与推荐资格规则

### 6.1 生命周期判定依据（分类别）

| 类别 | 依据 | 首期覆盖 |
| --- | --- | --- |
| CPU | Socket + 代际表；PassMark `release_date` 仅作辅助佐证（需核实字段来源） | 是 |
| GPU | Chipset 代际表；PassMark `release_date` 辅助 | 是 |
| MOTHERBOARD | Socket + Chipset 平台代际表 | 是（逐步） |
| MEMORY | DDR 代际（派生自 `speed`） | 是 |
| STORAGE | 接口/协议代际 | 是 |
| COOLER / CASE / PSU | 无可靠发布日期，默认 `UNKNOWN` | 允许 UNKNOWN |

**禁止**用 LLM 记忆或未经核实的推测补全；无法确定一律 `UNKNOWN`。

### 6.2 推荐资格规则（按类别分组）

| 类别组 | 规则 |
| --- | --- |
| CPU / GPU | `governance_status=VALID` 且 `lifecycle∈{CURRENT,MATURE}` → `ELIGIBLE`；`lifecycle=LEGACY` → `RESTRICTED`；`lifecycle=UNKNOWN` → `RESTRICTED`；`DISCONTINUED` → `EXCLUDED`；`governance∈{INVALID,CONFLICT}` → `EXCLUDED` |
| MOTHERBOARD / MEMORY / STORAGE | 兼容性关键字段齐全且 `governance∈{VALID,INCOMPLETE}` → `ELIGIBLE`；缺关键字段 → `RESTRICTED`；`INVALID/CONFLICT` → `EXCLUDED` |
| COOLER / CASE / PSU | 关键规格齐全 → `ELIGIBLE`（**`lifecycle=UNKNOWN` 不阻断**）；关键字段缺失 → `RESTRICTED`；`INVALID/CONFLICT` → `EXCLUDED` |
| 任意类别 | 人工覆盖优先；被标记 `ARCHIVED` 者进归档池，不参与求解 |

### 6.3 四类发布候选池

| 池 | 准入 |
| --- | --- |
| Standard Build Pool | `recommendation=ELIGIBLE` 且 `lifecycle∈{CURRENT,MATURE}` |
| Budget Build Pool | `recommendation=ELIGIBLE` 且具备可用跑分（CPU/GPU 必填），按性能档位分层；不读价格 |
| Legacy Upgrade Pool | `lifecycle=LEGACY` 且 `recommendation∈{ELIGIBLE,RESTRICTED}` |
| Archived Pool | `recommendation=ARCHIVED` 或 `governance∈{INVALID,CONFLICT}` 或 `lifecycle=DISCONTINUED` |

报告必须给出每类 UNKNOWN 数量与占比，以及每池数量。

## 7. CI 门禁方案（Q5）

### 7.1 现有事实

`.github/workflows/ci.yml` 目前只有 `frontend` / `admin` / `backend` / `agent` / `deploy` / `docs` 六类过滤；`scripts/**` 命中 `docs` 任务（只跑文档链接与环境变量校验），**没有 pytest 门禁**。

### 7.2 修改

1. `changes` 任务新增输出 `data`，过滤：`scripts/pc-config/**`、`data/pc-config/schema/**`、`data/pc-config/samples/**`、`data/pc-config/manifest/**`。
2. 新增 `data` 任务：Python 3.12 + `pip install pytest`，执行 `python -m pytest scripts/pc-config/tests -q`，再执行 `python scripts/pc-config/validate_dataset.py --schema-only --samples data/pc-config/samples`。
3. 全量数据处理不进云端 CI（无源数据盘）：提供 `scripts/pc-config/verify-release.ps1`，参数 `-DataDir`，依次跑 pytest → `inspect_dataset.py` → `validate_dataset.py` → `publish_candidates.py --dry-run`，失败即非零退出。
4. `docs` 任务保持对新文档的断链检查；新增长文档必须同时通过 `scripts/check-doc-links.ps1`。

## 8. 测试清单

| 覆盖点 | 测试文件 | 关键断言 |
| --- | --- | --- |
| 八类别 Schema | `tests/test_schema.py` | 每类必填字段缺失即失败；未知键进 `raw_specs` |
| 单位规范化 | `tests/test_normalize_units.py` | `120 W`→120、`2 TB`→2048、`DDR5-6000`→6000 |
| 缺失/异常参数 | 同上 | 缺失→`null`+`missing_reason`；异常值→`INCOMPLETE`，不猜 |
| MPN/同名重复 | `tests/test_deduplicate.py` | 冲突进 `conflicts.jsonl`，不自动合并 |
| ID 稳定性 | `tests/test_id_stability.py` | 现有 28 条 `hardware_id` golden 不变 |
| PassMark 匹配 | `tests/test_benchmark_mapping.py` | CPU/GPU/磁盘匹配方法、置信度、UNMATCHED 保留 |
| GPU 多对一 | 同上 | `match_scope=CHIPSET`，不产生 SKU 级断言 |
| 生命周期/资格 | `tests/test_lifecycle.py` | UNKNOWN 不自动 EXCLUDED；CURRENT 不自动 ELIGIBLE |
| 候选池发布 | `tests/test_pools.py` | 池只含规则命中记录；无跑分不进预算池 |
| 第三方导出 | `tests/test_export_contract.py` | 必备字段齐全；回填字段为占位 |
| 重复执行 | `tests/test_idempotency.py` | 两次运行产物 sha256 相同 |
| 原始数据不丢 | 同上 | `raw_specs` 与源行逐键一致 |
| 现有 28 条不受影响 | `tests/test_existing_catalog.py` | 用现有 `catalog.json` 反向校验映射 |

## 9. Git 基线处理计划（Q6）

1. **复核**：`git status --porcelain` + `git diff --stat` 逐组看 diff；任何无法判定职责的文件列入「待确认清单」，不提交、不删除。
2. **安全分支**：先提交到当前 `feature/pc-config-agent`，每提交一次即形成可回退点。
3. **分组提交**（按真实 diff 复核后微调，不强制五组）：
   1. `feat(agent): 用 PC 单配置图替换通用聊天工作流` — `agent-service/**`
   2. `feat(pcbuild): 新增 PC 求解、兼容性、报价与快照模块` — `application-service/**`
   3. `feat(frontend): 新增配置结果卡片与 build_result 解析` — `frontend/**`
   4. `chore(scripts): 新增 PC 配置数据脚本与本地开发工具` — `scripts/**`
   5. `docs(pc-config): 补充 PC 配置模块文档与四份 ADR` — `docs/adr/**`、`docs/pc-config/**`、`docs/planning/**`、`docs/quality/**`
   6. `docs: 同步四端契约与部署文档` — `docs/` 其余改动
4. **提交前验证**：对应服务门禁（Java `mvnw verify`、Agent `ruff/mypy/pytest`、前端 `lint:ci/type-check/test:coverage`）至少各跑一次；未通过不提交。
5. **基线确认**：`git status` 干净（或只剩「待确认清单」），再执行 `git switch -c feature/pc-config-data-governance`。

## 10. 完成标准

生成 `docs/quality/hardware-data-governance-report.md`，逐项给出：原始数量、清洗后数量、八类变化、重复数量、无效数量、缺失关键字段数量、PassMark 匹配数与成功率、Current/Mature/Legacy/Archived/UNKNOWN 分布、四池数量、第三方映射输入文件位置、未解决问题、对 Stage 9 的准备情况。

额外完成条件：

- 原始数据目录零写入（用文件 mtime/hash 佐证）。
- 重复执行两次产物一致。
- `scripts/pc-config/tests` 全绿且已进 CI `data` 任务。
- 在线服务零改动：`git diff` 不包含 `application-service/src/main/java`、`agent-service/app`、`frontend/src`。
