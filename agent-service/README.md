# agent-service

Python 对话编排服务：接收 SSE 请求，驱动 LangGraph 的 ReAct 图调用大模型与工具，会话状态持久化到独立的 PostgreSQL（测试可用内存）。只校验 Java 签发的 JWT，不签发生产 Token、不建用户表。

技术栈：Python 3.12 · FastAPI · LangGraph 1.x · LangChain OpenAI · PostgreSQL/pgvector（会话库）· Redis（可选）· structlog · Pydantic Settings · SSE。

## 启动

```powershell
# 1. 安装依赖（自动创建 .venv）
uv sync --frozen

# 2. 准备配置
Copy-Item .env.example .env
# 至少修改：LLM__API_KEY、AUTH__JWT_PUBLIC_KEY（Java 的 JWT_PUBLIC_KEY 公钥 PEM，私钥不下发）、STORAGE__BACKEND / STORAGE__POSTGRES_URL

# 3. 建库（会话表由应用启动时自动创建）
#    CREATE DATABASE agent_service;

# 4. 启动（Windows 必须用 run.py）
uv run python run.py
```

Linux/macOS 也可以 `uv run uvicorn app.main:app --reload --port 8000`。Windows 下必须用 `run.py`：它把事件循环切换为 Selector，否则 psycopg 异步驱动在 ProactorEventLoop 下直接报错。

容器内由 Dockerfile 直接跑 uvicorn，端口 `8000`，健康检查打 `/api/v1/health`。

## 验证

```powershell
curl http://127.0.0.1:8000/api/v1/health          # {"status":"ok","env":"dev","service":"agent-service","redis":"disabled"}
curl -X POST http://127.0.0.1:8000/api/v1/auth/dev-token -H "Content-Type: application/json" -d '{"user_id":"alice"}'
curl -N -X POST http://127.0.0.1:8000/api/v1/chat/stream -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"message":"现在几点","thread_id":"demo"}'
```

交互文档：`http://127.0.0.1:8000/docs`。

## 质量门禁

```powershell
uv --directory agent-service run ruff check app tests evals run.py
uv --directory agent-service run mypy
uv --directory agent-service run pytest -q --cov=app --cov-report=term-missing

# 评测脚手架：假模型模式零 API 费用（CI 使用），--real 才真实调用模型
uv --directory agent-service run python -m evals --fake
```

评测用例放在 `agent-service/evals/cases/*.yaml`，新增场景只改 YAML；字段与语义见 [agent-workflows.md](../docs/services/agent-service/agent-workflows.md) §11。

涉及 Redis 与数据库的用例需要真实服务（CI 使用 Service 容器）；本地无 Redis 时相关用例会失败，属环境缺失而非代码缺陷。

## 文档

| 文档 | 内容 |
| --- | --- |
| [architecture.md](../docs/services/agent-service/architecture.md) | 分层、生命周期、外部依赖、数据归属、已知问题 |
| [agent-workflows.md](../docs/services/agent-service/agent-workflows.md) | 图结构、上下文裁剪、工具治理、checkpointer、一次对话的完整时序 |
| [api-reference.md](../docs/services/agent-service/api-reference.md) | 8 个端点、SSE 事件、错误码总表、与 Java 的契约差异 |
| [environment-variables.md](../docs/deployment/environment-variables.md) | 全部环境变量（含 Agent 侧 `AUTH__*` / `STORAGE__*` / `LLM__*` / `MCP__*`）、校验规则、生产 fail-fast、已知配置缺陷 |

## MCP 接入（可选）

默认关闭（`MCP__ENABLED=false`），关闭时不导入 MCP SDK、不建连、零启动开销。模板只支持网关拓扑：MCP Server 清单在 `deploy/litellm/config.yaml` 的 `mcp_servers`，Agent 只连聚合端点 `{LLM__GATEWAY_BASE_URL}/mcp`；Solo 模式没有网关，因此不提供 MCP。工具命名为 `mcp__<tool>`（小写下划线，满足 OpenAI 函数名约束）并复用注册表治理；连接失败只降级告警，不影响对话。配置格式与降级规则见 [agent-workflows.md §12](../docs/services/agent-service/agent-workflows.md)。

## 可选 RAG（默认关闭）

默认关闭（`RAG__ENABLED=false`），关闭时不导入检索器模块、不发外部请求。开启后需配置 `RAG__RETRIEVER_MODULE`（模块须暴露 `create_retriever()`），启动期校验失败会拒绝启动；检索按 `user_id` / `roles` 在检索前过滤，命中结果以 `citations` SSE 事件返回，检索异常降级为无引用。接入方式见 [agent-workflows.md §15](../docs/services/agent-service/agent-workflows.md)。

内置 pgvector 检索器 `app.rag.knowledge.retriever` 在 `agent_service` 库内建 `kb_documents` / `kb_chunks` 两张表，检索时融合向量召回与全文召回。表结构见 `migrations/rag/20261116_001_create_knowledge_tables.sql`，回滚用同目录的 `*_rollback.sql`；`STORAGE__AUTO_SETUP=true` 时启动期也会幂等建表。种子卡片位于 `knowledge/cards/`，导入命令：

```powershell
uv run python scripts/import_knowledge_cards.py --dry-run   # 只统计切片
uv run python scripts/import_knowledge_cards.py             # 写库（需配置 RAG__EMBEDDING_MODEL / DIMENSIONS）
```

## 异步任务接口

[app/services/task_runner.py](app/services/task_runner.py) 提供 `TaskRunner` 协议（提交 / 查询 / 取消）与默认 `InlineTaskRunner`：默认在提交时同步执行并立即返回终态，行为与直接调用一致；不新增 HTTP 路由。接入方用 `set_task_runner()` 换成队列 / Worker 实现即可，调用方与路由无需改动；处理器按 `kind` 注册，模板不内置任何任务类型。详见 [agent-workflows.md §16](../docs/services/agent-service/agent-workflows.md)。

## 注意

- 本目录 `docs/` 目录不存在；README 历史索引的 `docs/01-*.md` ~ `docs/20-*.md` 均为死链，权威文档统一在根 `docs/services/agent-service/`。
- 生产环境（`APP_ENV=prod`）有 fail-fast 校验：`DEBUG` 必须为 false、`STORAGE__BACKEND` 必须为 postgres、`REDIS__REQUIRED` 必须为 true、CORS 不允许 `*`。
