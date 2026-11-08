# 数据 ETL 单一入口，脚本测试纳入 CI 独立门禁

## 背景

`scripts/pc-config/` 已承载 Stage 1–6 的数据准备职责：`pc_config_data.py`（共享解析器与 `hardware_id` 生成）、`normalize_specs.py`、`match_benchmarks.py`、`select_candidates.py`、`ingest_offers.py`，以及 `tests/test_pc_config_data.py`、`tests/test_offers.py`。Stage 8 要新增去重、生命周期分类、治理校验与候选池发布。现有 CI 只有 `frontend` / `admin` / `backend` / `agent` / `deploy` / `docs` 六类分流，`scripts/**` 只命中文档任务，**测试从未在 CI 里跑过**。

## 决策

1. 原地演进 `scripts/pc-config/` 为唯一 ETL 入口：复用现有模块与 `PC_DATA_DIR`，不新建第二套流水线，不为了改名而重命名既有入口。
2. 只为真正缺失的职责新增文件：`inspect_dataset.py`、`hardware_schema.py`、`deduplicate_hardware.py`、`map_benchmarks.py`、`classify_lifecycle.py`、`publish_candidates.py`、`validate_dataset.py`；新脚本必须 import 现有解析器，不得复制解析逻辑。
3. CI 新增 `data` 路径过滤与 `data` 任务：`scripts/pc-config/**`、`data/pc-config/schema/**`、`data/pc-config/samples/**`、`data/pc-config/manifest/**` 变化时，运行 `pytest scripts/pc-config/tests` 与 Schema/样本校验。
4. 全量数据验证不进云端 CI（runner 无源数据盘），由 `scripts/pc-config/verify-release.ps1 -DataDir <路径>` 提供可重复的本地验收入口。

## 考虑过的替代方案

- **新建 `scripts/pc-config-governance/`**：目录更整洁，但会形成两套解析口径，`hardware_id` 生成规则容易分叉。
- **重写替换整套脚本**：可以统一命名，但会丢掉已验证的解析器与两个测试文件，回归风险高于收益。
- **只做本地手动验证**：成本最低，但数据治理脚本会退化成"只有原作者知道怎么跑"的孤立工具。

## 影响

- 数据脚本成为受门禁约束的代码，评审时可要求补测试。
- 全量跑批仍然只能在工作站执行，故 `verify-release.ps1` 必须自包含：pytest、基线核查、Schema 校验、发布 dry-run 全部串起来，非零退出即失败。
- 测试 Fixture 必须是小体量固定样本，保证 CI 无源数据也能验证规则正确性。
