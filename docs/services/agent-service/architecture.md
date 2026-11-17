# Agent Service 架构

| 项 | 内容 |
| --- | --- |
| 适用范围 | `agent-service/` 的分层、生命周期、工具治理、数据归属与 PC 图接入 |
| 状态 | Current |
| 最后更新 | 2026-11-17 |
| 权威性 | 本文是 Agent 服务级事实源；节点行为见 [agent-workflows.md](./agent-workflows.md)，接口见 [api-reference.md](./api-reference.md) |
| 主要证据 | `app/main.py`、`app/api/**`、`app/services/turn.py`、`app/agent/**`、`app/services/pc_client.py` |

## 1. 结论先行

- Python 3.12 + FastAPI；唯一生产图是 `pc-config` 确定性流水线（默认 9 节点，开启多 Agent 后 11 节点）。
- HTTP 层只做鉴权、限流、输入护栏与协议转换；一轮对话的全部编排在 `app/services/turn.py`。
- 工具必须经 `tool_governance` 取得，统一超时、重试、角色、配额、脱敏与截断。
- 状态与消息分两层：LangGraph checkpointer 存图状态，业务表存会话与消息。
- 多 Agent（2 Specialist + Critic）与 RAG 知识库均已实现，默认关闭；开启后图增加 `specialist_panel` / `critic_review` 两个节点。

## 2. 目录结构

```text
agent-service/
├── app/
│   ├── main.py                  FastAPI 入口、生命周期、路由注册
│   ├── api/                     协议层：chat、sessions、auth、models、health、metrics
│   ├── core/                    配置、日志、异常、安全、SSE、中间件
│   ├── services/                turn 生命周期、pc_client、会话存储、锁、摘要、缓存
│   ├── agent/                   profile/registry、pc 图、工具治理、prompts
│   ├── rag/                     检索器接缝（默认 Noop）
│   └── models/                  Pydantic Schema
├── evals/                       评测入口、用例与断言
├── tests/                       单测与契约测试
└── run.py                       本地启动
```

## 3. 请求生命周期

```text
POST /api/v1/chat/stream
  → JWT 验签（RS256，公钥）
  → 输入护栏（长度、控制字符、注入）
  → 限流（Redis 固定窗口，可 fail-open）
  → turn.py
       ├─ 解析偏好片段、决定是否注入历史
       ├─ 获取 thread 锁（Redis）
       ├─ 调用 LangGraph.astream_events
       │    ├─ custom → reasoning / token
       │    └─ tool_events → tool_call / tool_result
       ├─ aget_state 读取最终状态
       ├─ 落库消息与产物
       └─ done / error
```

- 同一 `thread_id` 并发请求在锁等待超时后返回冲突错误，不并发写同一会话。
- 客户端断开时取消图任务；已产生的工具副作用不补偿，快照由 Java 侧 append-only。
- 错误统一 `{code, message, requestId}`，不泄露内部地址或堆栈。

## 4. 鉴权与令牌

| 令牌 | 来源 | 用途 |
| --- | --- | --- |
| 用户 Access Token | Java 签发 | 校验用户身份；`sub` 即 `user_id` |
| 服务令牌 | Java `/internal/v1/auth/exchange` | 调 Java 内部接口，`token_use=service` |
| `X-User-Token` | 当前请求的用户 Access Token | 用户维度内部接口（compose、快照读取） |
| dev-token | Solo 模式本地生成 | 仅本地体验，生产禁用 |

- 服务令牌按 `client_id` 缓存并单飞刷新，不随每轮请求重新兑换。
- `user_token` 只存在于 `TurnRequest`，不写入图状态、日志或业务表。

## 5. 工具治理

`get_governed_tool(name)` 统一包装：

| 能力 | 行为 |
| --- | --- |
| 白名单 | 只允许 Profile 绑定的工具 |
| 超时 | 单工具超时，`compose` 30s，其余 10s |
| 重试 | 只读工具最多 1 次；非只读工具不自动重试 |
| 配额 | 单轮工具调用上限与单工具配额 |
| 脱敏 | 日志与 SSE 预览去除令牌、Cookie、内部地址 |
| 截断 | 输出按工具上限截断，避免撑爆上下文 |
| 错误 | 统一 `ToolExecutionError` 安全文案 |

节点禁止直接使用 `httpx`；Java 访问只经 `PcApiClient`。

## 6. 存储

| 数据 | 位置 | 说明 |
| --- | --- | --- |
| 图状态 / 消息历史 | checkpointer | `MemorySaver` 或 `AsyncPostgresSaver` |
| 会话、消息、运行记录 | `agent_service` 业务表 | 由 `SessionStore` 统一写入 |
| 会话索引缓存 | 进程内 TTL / Redis | 可失效重建 |
| 分布式锁 | Redis | 同一 `thread_id` 串行 |

- `STORAGE__BACKEND=postgres` 时 checkpointer 使用连接池，必须 `autocommit=True`。
- `agent_service` 库不得访问 Java 的 `agent` 库；跨端只走 HTTP 契约。
- 不保存模型密钥、服务令牌或完整 JWT。

## 7. 模型与 Profile

| 项 | 值 |
| --- | --- |
| 默认模型 | `deepseek:deepseek-flash` |
| 网关 | LiteLLM，OpenAI 兼容 |
| 默认 Profile | `AGENT__DEFAULT_PROFILE=pc-config` |
| Profile 目录 | `AGENT__PROFILES_DIR=app/agents` |
| 图选择 | Profile 不能选图；`build_agent` 固定装配 `pc-config` |

模型运行时关闭时走 Agent 单例模型；开启时由 Java 控制面解析模型与凭证。

## 8. PC 图接入

- `app/agent/pc/graph.py` 定义 9 个默认节点与条件边；多 Agent 开启时额外注册 `specialist_panel` 与 `critic_review`。
- `app/agent/pc/nodes.py` 实现需求解析、校验、策略、检索、LLM 选型、质量评审、渲染。
- `app/services/pc_client.py` 封装 Java `/internal/v1/pc/**`。
- 选型在 `build_architect` 完成；Java 只提供事实与组装，不存在旧求解器或独立校验节点。
- 兼容规则与 `UNKNOWN` 语义见 [compatibility-rules.md](../../pc-config/compatibility-rules.md)。

## 9. 可观测与降级

| 能力 | 实现 |
| --- | --- |
| 结构化日志 | `request_id`、`user_id`、`thread_id`、节点、耗时、状态；敏感字段脱敏 |
| 指标 | `/api/v1/metrics` 暴露 Prometheus 文本 |
| SSE 心跳 | `AGENT__SSE_HEARTBEAT_SECONDS`，防代理超时断流 |
| 模型失败 | 解析回退正则；策略回退默认；选型明确失败，不伪造 |
| Redis 失败 | 限流可 fail-open；锁不可用则拒绝并发写 |
| RAG 未启用 | `search_knowledge` 返回空引用，不阻断主流程 |

## 10. 已知问题与边界

- 多 Agent 仅 2 个 Specialist + 只读 Critic；Power & Storage Specialist、Critic 修正、工具并行与人工审批流【未实现】。
- RAG 已有知识库与引用治理，默认关闭；rerank 与引用正确性回归【未完成】。
- MCP 仅有网关客户端接缝，默认关闭【未实现业务用途】。
- `--real` 评测未进 CI，语义回归依赖人工。
- 会话摘要与长期记忆只做上下文压缩，不是跨会话用户画像【未实现】。

## 11. 相关文档

- 工作流：[agent-workflows.md](./agent-workflows.md)
- 接口：[api-reference.md](./api-reference.md)
- PC 模块：[pc-config/README.md](../../pc-config/README.md)
- 总体架构：[architecture-overview.md](../../architecture-overview.md)
