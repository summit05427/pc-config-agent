# Agent 端架构

| 项 | 内容 |
| --- | --- |
| 状态 | 已验证（源码级） |
| 基线 | 分支 `fix/post-refactor-bugfix`，HEAD `397b1fb`，含未提交改动 |
| 最后核验 | 2026-11-01（§9 测试数字为 2026-10-31 快照，未复测） |
| 主要证据 | `agent-service/{pyproject.toml,Dockerfile,run.py}`、`app/main.py`、`app/{api,agent,services,core}/**`、`tests/*.py` |

## 权威文档导航

| 主题 | 权威文档 |
| --- | --- |
| 全仓文档入口 | [docs/README.md](../../README.md) |
| 系统架构、服务边界、通信链路 | [docs/architecture-overview.md](../../architecture-overview.md) |
| 对外 HTTP / SSE 契约、错误码映射 | [docs/api-contract.md](../../api-contract.md) |
| Agent 端点与错误码实现细节 | [api-reference.md](./api-reference.md) |
| Agent 图结构、裁剪、工具治理、时序 | [agent-workflows.md](./agent-workflows.md) |
| 环境变量（唯一定义与默认值来源） | [docs/deployment/environment-variables.md](../../deployment/environment-variables.md) |
| Agent 编码硬约束 | [.trae/rules-on-demand/30-agent-python.md](../../../.trae/rules-on-demand/30-agent-python.md) |

本文只描述本服务的结构事实；契约字段、环境变量与编码约束各由其权威文档承载，冲突时以代码为准。

## 1. 定位

对话编排服务：接收前端 SSE 请求，驱动 LangGraph 的 ReAct 图调用大模型与工具，并把会话状态持久化到独立的 PostgreSQL（或内存，测试用）。

**明确不负责**：用户注册登录、Token 签发、业务数据读写、权限模型定义。这些属于 Java 端；Agent 只校验 Java 签发的 JWT。

## 2. 技术栈

| 项 | 版本约束 | 证据 |
| --- | --- | --- |
| Python | `>=3.12` | `pyproject.toml` |
| FastAPI | `>=0.161.1` | 同上 |
| LangGraph | `>=1.2.16` | 同上 |
| LangChain OpenAI | `>=1.7.2` | 同上 |
| langgraph-checkpoint-postgres | `>=3.2.0` | 同上 |
| psycopg（pool + binary） | `>=3.3.6` | 同上 |
| redis[hiredis] | `>=8.1.0` | 同上 |
| PyJWT[crypto] | `>=2.15.1` | 同上 |
| pydantic-settings | `>=2.16.1` | 同上 |
| structlog | `>=26.1.0` | 同上 |
| tiktoken | `>=0.14.0` | 同上 |
| prometheus-client | `>=0.26.0` | 同上 |
| uvicorn | `>=0.54.0` | 同上 |
| 工具链 | uv / ruff（line-length 100，`E,F,I,UP,B,ASYNC`） / mypy（`files=["app"]`） / pytest（`asyncio_mode=auto`，覆盖率 `fail_under=90`） | `pyproject.toml` |

**已声明但零引用**：`mcp`、`langchain-mcp-adapters`、`python-multipart`、`openai`（`openai` 是 LangChain 的传递依赖，可直接引用但当前未用）。SSE 由 `sse-starlette` 的 `EventSourceResponse` 实现（2026-10-28 由自研编码器迁移，事件格式不变）。

## 3. 目录与分层

| 层 | 目录 | 职责 | 禁止 |
| --- | --- | --- | --- |
| 接口层 | `app/api/v1/` | 参数校验、鉴权依赖、SSE 编码、响应组装 | 写 SQL、直接建模型客户端、写业务规则 |
| Agent 层 | `app/agent/` | 图、状态、上下文裁剪、工具注册与治理、提示词、checkpointer | 处理 HTTP、读写请求对象 |
| 服务层 | `app/services/` | 可复用领域能力：LLM 客户端、会话元数据、历史消息存储、分布式锁、幂等、缓存 | 依赖 `api`、依赖具体路由 |
| 基础设施层 | `app/core/` | 配置、日志、中间件、鉴权、异常、Redis 客户端、key/TTL、指标 | 依赖任何业务模块 |

依赖方向 `api → agent / services → core`。自检方法：删除 `app/api/` 后，其余模块仍能正常 import。`app/main.py` 是唯一的装配层，可以同时引用 `agent` 与 `core`（`app_lifespan` 正是为此存在）。

## 4. 请求到响应的装配

`create_app()`（[main.py](file:///f:/agent-project-template/agent-service/app/main.py)）负责：

1. `configure_logging(settings)`；
2. **启动期校验提示词**：基础提示词与（开关开启时的）OpenUI 契约加载失败均抛 `RuntimeError`，让问题在进程启动时暴露；
3. 注册中间件（后添加的先执行，因此 CORS 在最外层）：

```
CORSMiddleware
  └ MetricsMiddleware（条件注册：METRICS__ENABLED）
      └ RequestIDMiddleware
          └ 路由
```

4. `register_exception_handlers` 挂 4 类处理器：`AppError` / `RequestValidationError` / `StarletteHTTPException` / `Exception`；
5. `include_router(api_router, prefix=API_PREFIX)`。

中间件选择纯 ASGI 实现而非 `BaseHTTPMiddleware`，原因是后者会对响应再包一层，历史上与流式响应存在缓冲/兼容问题，而本服务核心接口就是 SSE。

CORS：`allow_credentials=True` + 显式 `cors_origins` 白名单（默认 `http://localhost:5173`），`expose_headers` 暴露 `x-request-id`；`allow_methods` / `allow_headers` 为 `*`。

## 5. 生命周期

```
lifespan (AsyncExitStack)
  ├─ checkpointer_lifespan：memory → MemorySaver；postgres → 建池 + 自动 setup
  ├─ setup_session_store：复用 checkpointer 的连接池建 session_meta / session_messages；memory 后端走进程内适配器
  ├─ setup_usage_outbox：同一连接池建 usage_outbox（用量待投递事件）
  ├─ setup_session_deletion：同一连接池建 session_deletion_tasks（检查点删除墓碑；实现拆分为 `app/services/session_deletion/` 的队列适配器 + 后台 worker）
  ├─ redis_lifespan：未配置→告警跳过；REQUIRED=true 且连不上→拒绝启动
  └─ yield → 逆序释放连接池 + 停止用量投递循环与会话删除重试循环
```

- `AsyncExitStack` 保证任一依赖启动失败时已建立资源被依次释放。
- 顺序固定为 checkpointer 先于 Redis（`app_lifespan` 显式顺序写死）。
- 提示词、路径白名单、配置校验都在启动期完成，运行期不再重复判断。

## 6. 与外部系统的关系

| 对端 | 方向 | 当前事实 |
| --- | --- | --- |
| 前端 | 入站 | 经 Nginx `/agent/` 去前缀转发；浏览器直连 SSE |
| Java `application-service` | 单向信任 | 出站 HTTP 客户端仅在 `app/services/control_plane.py`：创建模型任务、上报用量、校验/兑换模型访问；必带服务令牌。同时共享 `AUTH__JWT_PUBLIC_KEY`（及 `AUTH__JWT_KID` / `AUTH__ISSUER` / `AUTH__AUDIENCE`）约定 |
| PostgreSQL（业务库） | 不访问 | 只连自己的 `STORAGE__POSTGRES_URL`，禁止查 Java 的 `agent` 库 |
| Redis | 可选依赖 | 幂等键、会话锁、可选缓存；未配置时按设计降级；会话列表与历史已迁至 Postgres，不再依赖 Redis |
| LLM Provider | 出站 | `ChatOpenAI`，进程内单例；未配置或占位符 → 503 |
| MCP Server | 无 | 依赖已声明，代码零引用 |

## 7. 数据归属

| 数据 | 存储 | 生命周期 |
| --- | --- | --- |
| 对话状态（messages） | checkpointer（`postgres` 或 `memory`） | 长期；memory 重启即丢 |
| 历史消息（可展示的窗口） | `session_messages` 表（每轮结束写入，主键 `(user_id, thread_id, seq)`；`thread_id` **只存客户端原始值**，隔离由 `user_id` 承担） | 长期；与 checkpointer 同库 |
| 会话元数据（thread_id、标题、最近活跃、会话级 `model_key`） | `session_meta` 表（每轮对话 upsert，主键 `(user_id, thread_id)`；`thread_id` 存客户端原始值；`model_key` 为 NULL 表示 Auto） | 长期；与消息表同库，列表与历史都不依赖 Redis |
| 幂等记录 | Redis `<prefix>:<env>:idempotency:...` | 默认 86400s |
| 用量待投递事件 | `usage_outbox` 表（主键 `invocation_id`；`pending`/`dispatched`/`dead`） | `dispatched` 保留 7 天；`dead` 保留待人工排查；**不是用量台账**，Java 为唯一事实源 |
| 会话删除墓碑 | `session_deletion_tasks` 表（主键 `(user_id, thread_id)`；`pending`/`completed`/`failed`/`cancelled`），实现在 `app/services/session_deletion/{interface,memory,postgres,worker}.py`（队列适配器 + worker） | `completed`/`cancelled` 保留 7 天、`failed` 保留 30 天；后台按退避重试删除检查点 |
| 会话锁 | Redis `<prefix>:<env>:lock:thread:<sha256(thread_id)>` | 默认 300s，不自动续期 |
| 用户身份 | **不落库** | 每次从 JWT 解析 |

## 8. 可观测

- 结构化日志（structlog）：每条请求绑定 `request_id` / `method` / `path`，鉴权后再绑 `user_id`；请求结束记录 `request.finished` 与耗时；`finally` 中 `clear_contextvars()` 防泄漏。
- 指标：13 个指标族，见 [api-reference.md](./api-reference.md) §6；标签只允许 method/route/status/tool/model/type，**禁止 user_id / thread_id**。
- 日志分级：`warning` 用于可恢复异常（Redis 探活失败、工具重试、幂等收尾失败），`exception` 只用于流内未预期异常与兜底 500，同一异常只打一次堆栈。

## 9. 测试结构

`tests/` 共 23 个文件：22 个 `test_*.py` + `conftest.py`，按能力拆分：

| 模块 | 覆盖面 |
| --- | --- |
| `test_chat_stream` | SSE 事件、幂等 409、锁、超时、断开 |
| `test_sessions` | 会话列表（`session_meta` + 标题）、重命名/删除、历史消息 `asc`/`desc`、分页、404、归属隔离、删除锁冲突 |
| `test_health` / `test_metrics` | 存活/就绪判定、指标输出（含 outbox Gauge/Counter） |
| `test_auth` | JWT 校验、401、dev-token 守卫 |
| `test_agent_graph` / `test_context` | 图结构、裁剪策略、token 估算 |
| `test_tool_registry` | 超时、重试、权限、错误包装 |
| `test_prompts` | 名称白名单、路径穿越、缺失/空文件 |
| `test_persistence` | memory/postgres 切换、setup、探活 |
| `test_model_usage` / `test_usage_outbox` | 批量投递、退避重试、dead 终态、降级内存、持久化跨重连、领取租约、purge |
| `test_session_deletion` | 墓碑入队、后台重试到 failed、检查点不支持删除、会话复用取消、锁冲突顺延、终态清理、Gauge、Postgres 跨重连与租约；实现拆分为 `app/services/session_deletion/` 包，测试只走公开 API |
| `test_control_plane` / `test_model_resolver` / `test_model_runtime` | 内部接口调用、服务令牌、运行时解析与降级、门面装配顺序 |
| `test_preferences` | 偏好提示词注入与长度限制 |
| `test_redis` / `test_redis_primitives` / `test_redis_primitives_integration` | 客户端生命周期、key/TTL、锁与幂等（真实 Redis） |
| `test_config` / `test_errors` / `test_llm` | 生产守卫、异常信封、LLM 配置校验 |

**测试数字为 2026-10-31 实测快照，未在 2026-11-01 复测，不得当作当前状态**：`pytest -q --cov=app` 共 303 例全部通过，总覆盖率 93.30%（阈值 `fail_under=90`）；`ruff check app tests run.py` 与 `mypy`（`files=["app"]`）均通过。`test_usage_outbox` 的 5 个与 `test_session_deletion` 的 5 个 PostgreSQL 用例在本地真实库执行，未跳过。需要当前数字时请重新执行 `.trae/rules` 与 `docs/development-rules.md` 中的门禁命令，不要引用本快照。

会话删除墓碑已按「队列 + worker」拆分：`app/services/session_deletion/` 下 `constants.py`（状态与重试常量）、`interface.py`（队列协议）、`memory.py` / `postgres.py`（两个适配器）、`worker.py`（领取、锁、退避与后台循环）；`app/services/session_deletion/__init__.py` 保留原模块级函数名做装配门面。

## 10. 已知问题与偏差

| 编号 | 问题 | 影响 |
| --- | --- | --- |
| A-01 | `.env.example` 的 `AUTH__JWT_ISSUER` / `AUTH__JWT_ALGORITHM` 与字段名不匹配 | **已解决（2026-10-28）**：统一改为 `AUTH__ISSUER` / `AUTH__ALGORITHM` |
| A-02 | `extra="ignore"` 让所有拼错变量静默失效 | 与「启动即校验」设计目标相悖 |
| A-03 | 4 个依赖声明但零引用（`mcp`、`langchain-mcp-adapters`、`python-multipart`、`openai`） | 镜像体积与供应链面增大，无功能收益 |
| A-04 | 会话锁不做自动续期，TTL 300s 是硬上限 | 单轮生成超过 300s 时锁会提前释放，并发写入风险（当前总超时 120s，尚未触发） |
| A-05 | 会话历史曾在内存中切窗，读取量随会话长度增长 | **已解决（2026-10-28）**：新增 `session_messages` 表，历史接口改为数据库侧窗口查询 |
| A-06 | 500 响应在 `DEBUG=true` 时返回异常类名与消息 | 仅 dev/staging 可接受；`prod` 配置守卫强制 `DEBUG=false` |
| A-07 | 再次暴露的旧文档死链：`agent-service/README.md` 索引的 `docs/01-*.md` ~ `docs/20-*.md` 全部不存在（`agent-service/docs/` 目录不存在） | 已在 README 改写中替换 |

## 11. 明确不存在的能力

无 RAG/向量检索（部署有 pgvector，代码未用）、无 MCP 工具接入、无多 Agent 编排、无人工审批节点、无 Token 刷新、无审计日志、无服务间鉴权重放防护。会话删除已实现，检查点删除通过 `session_deletion_tasks` 墓碑后台重试（实现见 `app/services/session_deletion/`，队列 + worker；审计 P1-06 已修复）。

## 12. 深模块检查表（2026-11-05 架构审查）

重构后固定按此表自查；违反项的修复方案记录在 `.trae/rules-on-demand/30-agent-python.md` §9。

| 检查项 | 当前落点 |
| --- | --- |
| 路由是否只做传输 | `app/api/v1/chat.py` 只保留参数校验、锁/幂等生命周期与 SSE 编码；回合编排在 `app/services/turn.py` |
| 请求级状态是否成对进入/退出 | `app/agent/tool_context.py` 的 `ToolTurn` 同时管理角色与工具调用计数，异常/超时/取消都会复位 |
| 状态机是否与调度分离 | `app/services/session_deletion/` = 协议 `interface.py` + 适配器 `memory.py` / `postgres.py` + `worker.py` |
| 多步装配是否收口 | `app/services/model_runtime.py::prepare_agent`（解析运行时 → 兑换凭证 → 构图，撤销时同步清图与模型实例缓存） |
| 跨原语规则是否单一实现 | `app/services/redis_value.py`（TTL、JSON 编解码、坏值删除）；锁保留 token / Lua 语义，不并入 |
