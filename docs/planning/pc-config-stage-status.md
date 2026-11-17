# PC 配置 Agent 重构方案 v1

| 项 | 内容 |
| --- | --- |
| 适用范围 | PC 配置从「Java 求解器选型」迁移到「Agent LLM 选型、Java 事实权威」的重构记录与后续计划 |
| 状态 | Current（主体与 RAG 代码已落地；RAG 默认关闭；多 Agent 未开始） |
| 最后更新 | 2026-11-17 |
| 权威性 | 本文记录重构目标、落地结果与边界；当前行为以代码与 [agent-workflows.md](../services/agent-service/agent-workflows.md) 为准 |

## 1. 背景

旧架构中，Agent 只解析需求并生成说明，最终组合由 Java 侧旧求解器搜索决定。问题有三点：

1. LLM 看不到真实候选，无法解释「为什么选它而不是另一件」。
2. Java 同时承担事实与选型，职责过重，且搜索/剪枝逻辑难以与 LLM 的解释对齐。
3. 需求变化（例如用户偏好、用途取舍）只能通过调整求解器参数间接表达。

## 2. 目标架构

```text
需求解析 → 需求校验 → [澄清门控] → 配置策略 → 候选检索
  → LLM 选型（build_architect）→ 质量评审 → [兼容性门控] → 解释与渲染
```

职责边界：

| 角色 | 权力 | 不做什么 |
| --- | --- | --- |
| Agent LLM | 在候选集内决定 8 类 `hardware_id`；解释取舍 | 不改价格、型号、链接与兼容结论 |
| Agent 确定性代码 | 路由、质量评审、渲染、HITL、失败兜底 | 不替 LLM 选型 |
| Java | 候选、跑分、报价、组装、9 条兼容校验、预算、快照 | 不搜索、不评分选优、不生成说明 |

## 3. 落地结果

| 设计点 | 落地 | 证据 |
| --- | --- | --- |
| 9 节点图 | 已实现 | `app/agent/pc/graph.py` |
| 需求解析与正则兜底 | 已实现 | `nodes.py::requirement_parser` |
| 配置策略 | 已实现，模型失败用默认策略 | `nodes.py::build_strategist`、`strategy_source` |
| 候选检索 | 8 类并发 + 跑分/报价补充 | `nodes.py::candidate_retriever` |
| LLM 选型 | `BuildProposal` + 候选校验 + 增量校验 + `compose` + 最多 2 次修正 | `nodes.py::build_architect` |
| 质量评审 | 确定性规则，最多重选 1 次 | `quality.py` |
| 兼容性 | 9 条规则，`UNKNOWN` 一等状态 | `CompatibilityRule.java` |
| HITL | 澄清与兼容确认两个门控 | `hitl.py` |
| 解释与渲染 | LLM 说明 + 确定性 Markdown/OpenUI | `nodes.py::response_generator`、`renderer.py` |
| 评测 | `--fake` / `--real` | `agent-service/evals/` |
| 旧求解器路径 | 已删除：无旧求解器节点、选型工具与求解端点 | `PcBuildInternalController.java` |
| RAG | 已实现（pgvector 混合检索、入库脚本、`search_knowledge` 注入），默认关闭；缺 embedding 部署与外部语料，离线评测集已建 | `app/rag/knowledge/`、`evals/rag_eval.py` |
| 多 Agent | 规划中 | — |

### 3.1 Stage 1 门禁快照（2026-11-17）

| 口径 | 实测 | 结论 |
| --- | --- | --- |
| p95 时延 | 36.5s（多轮用例两轮合计） | 达标（≤120s） |
| 单轮 LLM 调用 | 最大 5 次 | 压线达标（≤5） |
| 单次成本 | 最高约 ¥0.14 | 达标（≤¥0.3） |
| 硬约束通过率 | 100%（7 个产出配置用例） | 达标 |
| 修正成功率 | 待按新口径（排除负向用例）全量复测 | 待确认 |
| 质量评审通过率 | 待首次采集 | 替代口径见 [ADR 0029](../adr/0029-stage1-quality-gate-baseline-alternative.md)（目标 ≥90%） |
| 质量分基线 | 求解器已删除且基线未留档 | 已按 [ADR 0029](../adr/0029-stage1-quality-gate-baseline-alternative.md) 豁免基线对比判据 |

数据来源：`agent-service/evals --real` 全量 15 条（14 通过，唯一失败为 8000 元整机跨代际选型，已修复并单例验证）。

## 4. 关键设计取舍

### 4.1 为什么不让 LLM 直接调用价格接口

LLM 只看到候选摘要（含决策字段），价格与链接由 Java 在 `compose` 时注入。模型输出 Schema `extra="forbid"`，出现价格/型号/链接字段直接判非法，避免模型复述或编造。

### 4.2 为什么保留质量评审

Java 只保证「装得下、预算内」，不保证「搭得合理」。低端 CPU 配旗舰显卡、办公场景买高端独显都能通过兼容校验，因此用确定性规则兜住质量底线，并把可修正问题转成结构化反馈。

### 4.3 为什么 `UNKNOWN` 不阻断

字段缺失是数据问题，不是用户配置错误。`UNKNOWN` 必须展示「待核验」，但不阻止生成方案；只有 `FAIL` 是硬冲突。

### 4.4 为什么删除求解器

线上选型权已迁移到 LLM；保留双路径会产生两套状态、提示词与评测。旧求解器类仅保留取价与草稿组装两个事实辅助方法，不再搜索。

## 5. 未完成项

| 项 | 状态 | 下一步 |
| --- | --- | --- |
| RAG 知识库 | 规划中 | 确认语料来源与许可；接入 pgvector；定义引用格式 |
| 多 Agent（Specialist / Critic） | 规划中 | 单图稳定后再评估拆分，不提前引入 |
| 多方案对比与交互式换件 | 未实现 | 需要前端与快照链路改造 |
| 报价核验闭环 | 未实现 | 补 `OWNER_VERIFIED` 与过期清理 |
| 真实模型评测门禁 | 未实现 | 先扩用例，再评估 CI 成本 |

## 6. 验收口径

- 选型：`BuildProposal` 恰好 8 类，`hardware_id` 全部在候选集内。
- 事实：总价等于 8 件最低有效报价之和；兼容报告 9 条齐全。
- 安全：模型文案不含数字、型号、价格、渠道；非 `PASS` 不得宣称兼容。
- 降级：模型不可用时明确失败或确定性兜底，不伪造 LLM 结果。
- 评测：`--fake` 全绿；`--real` 由人工执行并记录基线。

## 7. 相关文档

- [agent-workflows.md](../services/agent-service/agent-workflows.md)
- [compatibility-rules.md](../pc-config/compatibility-rules.md)
- [roadmap.md](./roadmap.md)
- [ADR 0028](../adr/0028-llm-led-build-selection.md)
