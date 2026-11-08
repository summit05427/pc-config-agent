# Stage 8 只产出离线治理资产，不接入运行时

## 背景

[BuildSolver](../../application-service/src/main/java/com/example/agent/pcbuild/application/BuildSolver.java) 的候选池只接受**存在可用报价**的硬件（`buildPool` 中 `offer == null` 直接 `continue`），并且已限流为 CPU/GPU 各 12 个、其余各 8 个。Stage 8 产出的是无价格的主数据与候选池；第三方商品映射要到 Stage 9 才有。若本期改 Repository 去读大候选池，在线推荐结果不会变化，却会破坏 `PcFixtureRepositoryTests` 的既有计数断言。

## 决策

1. Stage 8 不修改 `pcbuild` 模块任何代码、不新增 Java 只读接口、不替换 classpath `catalog.json`、不调整既有测试断言。
2. Stage 8 不承诺在线推荐覆盖率提升，验收口径是"标准化硬件资产可发布、可追溯、可重复生成"。
3. Stage 9 承担第三方商品导入、`hardware_id` 关联、数据验证与 `OfferRepository` 接入；只有 Stage 9 完成后才评估治理数据对推荐的实际改善。
4. Stage 8 必须保证 `hardware_id` 稳定，作为 Stage 9 的唯一回关联键。

## 考虑过的替代方案

- **新增 Java 只读接口暴露候选池**：当前没有消费者，属于提前建设；接口一旦发布就要维护契约。
- **直接替换 `catalog.json` 为全量数据**：会撞上"无报价即无候选"，求解结果不变，却让夹具测试与启动体积同时变差。

## 影响

- Stage 8 是一个纯离线交付物，评审时不应以"推荐变好了吗"作为验收问题。
- 候选池的价值在 Stage 9 才被验证；这也意味着 Stage 8 的池规则需要写成可回放的规则文件与版本号。
- 边界清晰，回滚成本极低：删掉 `data/pc-config/` 与脚本即回到当前状态。
