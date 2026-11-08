---
alwaysApply: true
---

# Agent 规则（agent-service/**）

适用范围：仅 `agent-service/**`。其他目录忽略本文件；公共约束见 `00-monorepo-common.md`。

## 1. 技术基线

Python 3.12 + FastAPI + LangGraph + LangChain OpenAI + uv + ruff + mypy + pytest + PostgreSQL/pgvector + structlog + Pydantic Settings + SSE。

## 2. 分层与命名

| 层 | 目录 | 职责 | 禁止 |
| --- | --- | --- | --- |
| 接口层 | `app/api/v1/` | 参数校验、鉴权依赖、响应组装、SSE 编码 | 写 SQL、直接创建模型客户端、写业务规则 |
| Agent 层 | `app/agent/` | 图结构、状态、工具、checkpointer | 处理 HTTP、读写请求对象 |
| 服务层 | `app/services/` | 可复用的领域能力（LLM 客户端、会话存储、控制面调用） | 依赖 `api`、依赖具体路由 |
| 基础设施层 | `app/core/` | 配置、日志、中间件、鉴权、异常 | 依赖任何业务模块 |

单向依赖：`api → agent / services → core`。判断方法：删掉 `app/api/` 后，其余模块仍能正常 import。

命名：模块/函数/变量 snake_case；类 PascalCase；常量 SCREAMING_SNAKE_CASE；Pydantic 模型用 `XxxRequest` / `XxxResponse`。禁止无意义缩写与单字母变量（循环计数除外）。

## 3. 配置

- 所有配置走 `app/core/config.py` 的 Pydantic Settings，嵌套变量用 `__`（如 `STORAGE__POSTGRES_URL`）。
- 密钥只从环境变量或 `.env` 读取；`.env` 不提交，`.env.example` 必须同步。
- `APP_ENV=prod` 时 `DEBUG=false`；JWT 只持公钥（`AUTH__JWT_PUBLIC_KEY`），禁止注入签名私钥；占位符公钥/LLM Key 不得进入生产。
- Agent 只验证 Java 签发的 JWT，算法固定 RS256，校验签名、`kid`、`exp`、`sub`、`iss`、`aud`、`token_use`；不建用户表、不签发生产 Token。
- 本地 pgvector 端口 `5433`；容器内用 `pgvector:5432`；不要连 Java 的 `postgres:5432`。

## 4. 会话与数据

- `thread_id` 是客户端标识，业务表以 `(user_id, thread_id)` 隔离并保存原始值；checkpointer 与分布式锁必须使用 `namespaced_thread_id(user, client_thread_id)` 派生的键，不得直接把客户端值用于锁或图状态键。
- 会话持久化有两条：业务表（`session_meta` / `session_messages`，经 `app/services/`）与 LangGraph checkpointer（图状态）。禁止在路由里直接写这两类存储，统一经 service 层。
- SQL 全部参数化；禁止查询 Java 的 `agent` 业务库。
- 只持久化对话所需状态，禁止把 Token、API Key、完整敏感对话写入数据库。

阅读顺序：[docs/README.md](../../docs/README.md) → `docs/services/agent-service/{architecture,agent-workflows,api-reference}.md`；涉及 `/internal/v1/**` 时读 `docs/api-contract.md` §5.6。

## 5. 异步与 SSE

- 路由与工具使用 `async`；禁止在事件循环中做阻塞 I/O 或同步 SDK 调用。
- SSE 事件固定为 `token` / `tool_call` / `tool_result` / `done` / `error`。
- 流开始后 HTTP 状态码已固定为 200，流内错误只能发 `error` 事件。
- 客户端断开时停止图执行，避免无效模型调用与计费。
- 工具调用必须有超时与异常兜底，禁止无限循环；遵守 `recursion_limit`。

## 6. 日志与错误

- 使用 structlog，绑定 `request_id` 与 `user_id`；禁止打印 Token、API Key、完整对话内容。
- 业务错误统一用 `AppError`（`code` + `status_code`）；同一异常只记录一次堆栈。
- 未配置 LLM、Provider 不支持等返回 503，响应中不泄露上游密钥或内部堆栈。
- 日志级别：`error` 仅用于需人工介入的故障，`warning` 用于可恢复降级。

## 7. 测试与门禁

- 依赖安装：`uv --directory agent-service sync --frozen`。
- 静态检查：`uv --directory agent-service run ruff check app tests evals run.py`。
- 类型检查：`uv --directory agent-service run mypy`。
- 单测：`uv --directory agent-service run pytest -q --cov=app --cov-report=term-missing`。
- 评测：`evals/` 用例默认只跑假模型 `uv --directory agent-service run python -m evals --fake`（零 API 费用）；`--real` 有真实费用，仅手动执行，不进 CI。
- 覆盖率阈值 90%；数据库与 Redis 测试必须连真实服务（CI 使用对应 Service），禁止 skip 换取通过。
- 每个分支覆盖：成功、参数非法、未认证、资源不存在、上游失败。
- 测试方法名表达「场景 + 预期」；异步测试由 `asyncio_mode = "auto"` 接管。

## 8. Docker 与联调

- 容器端口 `8000`；健康检查 `/api/v1/health`。
- 关键环境变量：`APP_ENV`、`DEBUG`、`AUTH__JWT_PUBLIC_KEY`、`AUTH__JWT_KID`、`AUTH__ISSUER`、`AUTH__AUDIENCE`、`STORAGE__POSTGRES_URL`、`REDIS__URL`、`REDIS__REQUIRED`、`LLM__API_KEY`、`LLM__BASE_URL`、`LLM__MODEL`。
- Redis 只作为通用基础设施（连接池、key/TTL 约定、健康探测）；业务策略不得下沉到 `app/core/`。
- Nginx 将 `/agent/` 去掉前缀后转发；新增路由必须挂在 `API_PREFIX` 下。
- 修改契约时同步前端类型、Java DTO 与根 `docs/`。

## 9. 深模块与架构约束

以下条款来自 2026-11-05 架构审查的返工，新增与重构代码必须遵守：

- **路由只做传输**：`app/api/v1/` 只处理参数校验、鉴权、锁/幂等生命周期与 SSE 编码；回合编排放 `app/services/turn.py`，运行时装配放 `app/services/model_runtime.py`，持久化放 `app/services/session_store/`。
- **状态成对进入/退出**：角色、调用计数等请求级状态只能由同一个上下文管理器（如 `ToolTurn`）进入并在退出时整体复位；禁止并列的 `start_*` / `reset_*` 函数，避免异常路径只复位一半。
- **状态机与调度分离**：墓碑、队列类逻辑拆成「协议 + 内存/持久化适配器 + worker」；测试只走公开 API，禁止直接读写模块私有字典或内部任务列表作为后门。
- **装配顺序收口**：多步装配（解析运行时 → 兑换凭证 → 构图）只能由一个门面暴露；失败清理（如凭证撤销时同时清图与模型实例缓存）必须放在同一处。
- **公共规则单一实现**：TTL 校验、JSON 编解码、坏值「告警 + 删除 + 返回 None」等跨原语规则只允许一份（`app/services/redis_value.py`）；锁的 token / Lua 语义不同，保持独立，不强行合并。
- **保留可观测契约**：合并重复实现时保留原错误文案与日志事件名（如 `cache.invalid_value`、`idempotency.invalid_value`），并为共享模块补直接单测。
