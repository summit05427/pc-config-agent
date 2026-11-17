# PC 配置模块架构

| 项 | 内容 |
| --- | --- |
| 适用范围 | PC 配置模块的三端职责、调用链与选型权边界 |
| 状态 | Current |
| 最后更新 | 2026-11-17 |
| 权威性 | 本文描述模块级架构；系统总体架构以 [docs/architecture-overview.md](../architecture-overview.md) 为准，接口字段以 [docs/api-contract.md](../api-contract.md) §5.7 为准 |
| 主要证据 | `agent-service/app/agent/pc/`、`agent-service/app/services/pc_client.py`、`application-service/.../pcbuild/**` |

## 1. 结论先行

- **选型权在 Agent 侧 LLM**：`build_architect` 读取候选、策略与需求，输出 8 类 `hardware_id` 的 `BuildProposal`。
- **事实权威在 Java**：候选、规格、跑分、最低有效报价、组装、9 条兼容校验、预算校验与快照全部由 Java 判定。
- Java **不提供**求解/选型接口，也不做搜索、评分选优或方案比较。
- Agent 不访问 Java 数据库、不自行算价、不伪造链接；LLM 输出中的价格/型号/链接字段会被 Schema 直接拒绝。

## 2. 选型权与事实权威

| 能力 | 归属 | 说明 |
| --- | --- | --- |
| 决定「选哪一个 `hardware_id`」 | Agent LLM | 只在候选集内选择；候选集外 ID 判为 `CANDIDATE_NOT_IN_POOL` |
| 需求解析与澄清 | Agent | `requirement_parser` + `requirement_validator` |
| 配置策略 | Agent LLM | `build_strategist`，失败时用确定性默认策略并标 `DEFAULT` |
| 候选、规格、跑分 | Java | `/internal/v1/pc/hardware/**`、`/benchmarks` |
| 报价与最低有效价 | Java | `/offers`、`compose` 内部取价 |
| 组装与快照 | Java | `POST /builds/compose` |
| 兼容性 | Java | `/builds/validate`、`/builds/validate-partial`；规则见 [compatibility-rules.md](./compatibility-rules.md) |
| 质量评审（搭配合理性） | Agent 确定性代码 | `quality.py`，只补充「搭得合不合理」 |
| 自然语言解释 | Agent LLM | `response_generator`；正文由渲染器用 Java 字段组装 |

## 3. 三端职责

| 端 | 负责 | 不负责 |
| --- | --- | --- |
| Frontend + Nginx | 唯一公网入口；会话、SSE 消费、`BuildResultCard`、HITL 表单 | 不选硬件、不算价格、不拼接鉴权 |
| Agent Service | 需求解析、策略、候选编排、LLM 选型、质量评审、HITL、解释与渲染 | 不查 Java 数据库、不自算价格、不签发 Token |
| Java Application Service | 硬件目录、跑分、报价、组装、兼容性、预算、快照 | 不调用 Agent、不做 LLM 选型、不生成自然语言说明 |

## 4. 调用链

```text
浏览器
  → frontend Nginx
  → POST /agent/api/v1/chat/stream（SSE）
  → Agent turn.py
  → PC 图 9 节点（两个 HITL 门控默认直通）
  → 治理后工具 app/agent/pc/tools.py
  → PcApiClient app/services/pc_client.py
  → Java /internal/v1/pc/**（服务令牌 + 按需 X-User-Token）
  → pcbuild：Repository / BuildSolveService / CompatibilityValidator / Snapshot
```

- 内部接口只走容器内网，不经 Nginx，不对外暴露。
- `compose` 与 `GET /builds/{buildId}` 属于用户维度，必须带 `X-User-Token`；`validate` 与 `validate-partial` 不落库、不要求用户令牌。
- 服务令牌复用 `control_plane` 的缓存与单飞刷新。

## 5. 为什么是确定性单图

- 目标是不超支、不虚构链接、已知冲突不进入成功方案；让 LLM 自由决定调用哪个工具无法保证这些约束。
- 图节点顺序、路由条件、修正上限都在代码里，可单测、可复现。
- LLM 的自由度只放在「在候选集中选哪些 ID」与「怎么解释」，事实计算仍由 Java 完成。
- 决策背景见 [ADR 0027](../adr/0027-pc-config-decisions.md) 与 [ADR 0028](../adr/0028-llm-led-build-selection.md)。

## 6. 与旧求解器路径的关系

- 旧求解器节点、旧选型/校验工具与旧求解端点均已移除。
- 旧求解器类只保留「最低有效报价聚合」与「草稿组装」两个事实辅助方法，不再搜索或评分选优。
- 旧求解器的评测数字与文档不再作为现状引用。

## 7. 未实现能力

- 多 Agent 骨架已实现（Performance / Platform + Critic），默认关闭；缺 Power & Storage Specialist、Critic 受限修正与 A/B 对照。
- RAG 检索链路已实现并本地验证（默认关闭）；rerank 与引用正确性回归未完成。
- 多方案对比、瓶颈分析、交互式换件、历史价格曲线、管理端硬件维护页【未实现】。
- 自动报价采集与过期清理【未实现】。

## 8. 相关文档

- Agent 工作流：[agent-workflows.md](../services/agent-service/agent-workflows.md)
- 兼容规则：[compatibility-rules.md](./compatibility-rules.md)
- 数据与报价：[data.md](./data.md)、[market-offer-management.md](./market-offer-management.md)
- 评测：[testing-and-evaluation.md](./testing-and-evaluation.md)
