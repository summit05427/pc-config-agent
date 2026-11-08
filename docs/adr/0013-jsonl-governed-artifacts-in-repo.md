# 治理产物以仓库内 JSONL 为权威，Parquet 仅作派生

## 背景

Stage 8 要把 8,238 条 PCPartPicker 硬件与 25,318 条 PassMark 跑分加工为可追溯、可重复生成的主数据。现有在线链路只读取 `application-service/src/main/resources/pc-config/catalog.json`（28 条），其加载器 [JsonFixtureLoader](../../application-service/src/main/java/com/example/agent/pcbuild/infrastructure/JsonFixtureLoader.java) 在启动期一次性读入 classpath，无法承载全量治理产物。数据包附带的 `01_schema.sql` 是 MySQL 8 语法，而仓库基础设施只有 PostgreSQL。

## 决策

1. 治理产物落在仓库内 `data/pc-config/`，**JSONL 是唯一权威格式**，可审查、可 diff、可逐行追溯；Parquet 只作为分析用派生格式，不进入权威链路。
2. 原始数据继续保留在外部只读目录（`PC_DATA_DIR`），不复制、不改写、不提交。
3. 每次发布写入 `manifest/catalog-manifest.json` 与 `manifest/history/<batch_id>.json`，记录 `catalog_version`、`batch_id`、`generated_at`、输入文件 sha256、脚本 sha256、八类计数与 `distribution_status`。
4. 来源许可未核实前 `distribution_status=INTERNAL_ONLY`，`.gitignore` 排除 `master/`、`pools/`、`export/`、`staging/` 的全量文件，版本库只提交 Schema、脚本、Manifest、统计报告与固定样本。

## 考虑过的替代方案

- **PostgreSQL 新建 `hardware_master` schema**：查询能力最好，但让离线 ETL 依赖运行时数据库，违背"Agent 不承担全量 ETL"的边界，也让"重复执行可复现"难以用文件哈希验证。
- **继续只扩展现有 classpath `catalog.json`**：改动面最小，但 8,238 条会显著增大 jar，且每次数据刷新都要重新打包部署。
- **把全量原始 CSV 直接提交进仓库**：最简单，但约 19MB CSV + 约 50MB 原始归档会让仓库长期膨胀，且许可未确认前存在再分发风险。

## 影响

- 数据发布不依赖数据库，任何人可离线复现；代价是查询需要按行扫描，故 `hardware_id` 必须建索引文件（后续阶段按需增加）。
- 阶段 9 接入报价时，可直接消费 JSONL 或预加载进数据库，不改变硬件主数据的权威性。
- 许可状态成为发布流程的一等公民：`INTERNAL_ONLY` 期间仓库中看不到全量数据，必须通过 manifest 与报告判断数据规模。
