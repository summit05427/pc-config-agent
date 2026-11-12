# PC 配置模块架构

| 项 | 内容 |
| --- | --- |
| 状态 | 已验证（Stage 1–5 完成） |
| 最后核验 | 2026-11-08 |
| 权威性 | 本文件描述 PC 模块的三端职责与调用链；系统总体架构以 [docs/architecture-overview.md](../architecture-overview.md) 为准 |
| 主要证据 | [PC 配置模块决策合并记录](../adr/0027-pc-config-decisions.md)、`agent-service/app/agent/pc/`、`agent-service/app/services/pc_client.py` |

## 1. 三端职责

| 端 | 负责 | 不负责 |
| --- | --- | --- |
| Frontend + Nginx | 唯一公网入口；会话、历史、模型选择、偏好、SSE 消费、`BuildResultCard` 与 Markdown 回退 | 不选硬件、不算价格、不拼接鉴权、不保存模型密钥 |
| Agent Service | 需求解析、装载、编排、确定性渲染、工具事件翻译 | 不访问 Java 数据库、不自选 SKU、不签发 Token |
| Java Application Service | 硬件目录、跑分、报价、兼容性校验、确定性求解、预算与快照落库 | 不调用 Agent、不生成自然语言配置说明 |

术语边界见 [glossary.md](./glossary.md)；HTTP / SSE 字段以 [docs/api-contract.md](../api-contract.md) §5.7、§7 为唯一来源。

## 2. 调用链

```text
浏览器
  → frontend Nginx
  → POST /agent/api/v1/chat/stream（SSE）
  → Agent chat.py / turn.py
  → PC 图八节点（两个 HITL 门控默认直通）
  → 治理后工具（app/agent/pc/tools.py）
  → PcApiClient（app/services/pc_client.py）
  → Java /internal/v1/pc/**（服务令牌 + X-User-Token）
  → pcbuild 模块（Repository / Solver / CompatibilityValidator / Snapshot）
```

- 内部接口只走容器内网，不经 Nginx，不对外暴露；鉴权沿用服务令牌，用户维度接口额外带 `X-User-Token`。
- 求解与快照读取属于用户维度，缺少用户令牌时工具层直接返回安全错误，不做匿名代查。
- 服务令牌复用 `control_plane` 的缓存与单飞刷新，PC 客户端不重复实现换取逻辑。

## 3. 为什么用确定性单图

- 产品硬指标是「零超支、零虚构链接、已知冲突不进入成功方案」。让 LLM 自主决定调用哪个工具或跳过求解，无法保证这些指标。
- 因此只保留一条固定流水线：节点顺序、路由条件与重解上限都在代码里，可单测、可复现。
- 通用 ReAct 图与 PC 图并存会产生两套 State、Prompt 与测试的长期成本，决策与替代方案见 [PC 配置模块决策合并记录](../adr/0027-pc-config-decisions.md) §1.1。

## 4. LLM 只做两件事

| 节点 | LLM 职责 | 代码约束 |
| --- | --- | --- |
| `requirement_parser` | 把自然语言解析成 `PCRequirements` JSON | 调用打 `TAG_NOSTREAM`；解析失败或模型不可用时退化为正则 + 关键词兜底 |
| `response_generator` | 生成一段不含数字、型号、价格的推荐说明 | 输出经 `_safe_reason` 过滤；命中数字、渠道、型号或超长时丢弃，改用确定性文案 |

- Markdown 正文由 `renderer.py` 用 Java 结构化字段渲染，不经 LLM 复述。
- 型号、价格、总价、SKU、链接全部来自 `BuildResult`；LLM 不接触这些字段。

## 5. 求解与快照归属

- 求解器在 Java `pcbuild` 模块内完成候选过滤、兼容性剪枝、预算剪枝与场景评分；金额全程使用整数分。
- 求解成功后在同一业务事务写入 append-only 表 `pc_build_snapshots`（Flyway `V24`），返回 `build_id`。
- `GET /internal/v1/pc/builds/{buildId}` 按用户校验归属；Agent 本期不展示历史快照列表。
- Agent 状态只保存当次 `build_result`，不保存完整商品列表或数据库副本。

## 6. 与旧 ReAct 图的替换关系

- `build_agent` 保留函数名与签名，但内部改为装配 `build_pc_graph`；`get_agent` / `get_agent_for_runtime` 的缓存语义不变。
- `model` / `tools` 节点、`ToolNode`、`tools_condition` 已删除；不再有 workflow dispatcher。
- Profile 加载与校验机制保留，仓库只保留 `pc-config.yaml`；未知 `agent_id` 仍返回 404。
- 聊天传输层、会话存储、模型运行时、鉴权、偏好与会话级模型选择均保留。

## 7. 未实现能力

- 多方案对比、瓶颈分析、交互式硬件替换【未实现】。
- 硬件数据版本化、历史价格曲线、自动报价采集【未实现】。
- 管理端硬件 / 商品维护页面【未实现】。
- Agent 侧 `PROGRAMMING` / `WORKSTATION` 场景解析【未实现】；Java 求解器已支持。
- HITL 已实现（默认关闭，见 [agent.md](./agent.md) §11）；RAG、MCP、多 Agent 编排【未实现】，不属于本期演示范围。
