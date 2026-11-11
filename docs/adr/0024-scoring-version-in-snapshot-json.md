# 评分策略版本写入快照 JSON，不新增数据库列

## 背景

Stage 10 要求工作负载评分策略可版本化，以便历史配置能还原“当时按什么规则打分”。当前 `pc_build_snapshots`（V24）只有 `solver_version`、`compatibility_rule_version`、`catalog_version` 三个版本列，没有评分策略与用途画像。

评分策略变化比求解算法更频繁（权重、加成系数、用途映射都会调），如果每次调参都要写迁移，迁移会被当成业务发布的一部分，回滚成本被放大。

## 决策

1. 新增常量 `ScoringPolicyVersion.SCORING_VERSION`，与 `solver_version`、`compatibility_rule_version` 分开递增。
2. 该版本与最终生效的 `workload_profile`（含用户是否显式指定）写入现有 `requirements_snapshot` JSON，不新增数据库列。
3. 若将来出现“按评分版本查询历史方案”的需求，再补列并从 JSON 回填。

## 考虑过的替代方案

- **新增 `scoring_version`、`workload_profile` 两列**：可查询、可建索引，但需要 V25 迁移、回滚脚本与历史行回填；当前没有任何按这两列过滤的查询需求。
- **不单独版本化，复用 `solver_version`**：评分调参会被误判为求解算法变化，历史结果是否“可比较”的判断失真。

## 影响

- 历史快照的评分依据只能通过解析 `requirements_snapshot` 获得，读取方不得假设该字段存在于表列中。
- 快照 append-only 语义不变：评分策略升级不会重写任何历史快照。
- 契约文档与 `docs/pc-config/solver-and-compatibility.md` 需要补充“评分版本存在 JSON 内”的说明，避免后续实现者按列查询。
