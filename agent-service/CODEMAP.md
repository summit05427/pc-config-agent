# agent-service 代码地图
用途：只做定位索引，不是规范；编码约束见 .trae/rules-on-demand/30-agent-python.md，接口契约见 docs/api-contract.md。

## 入口
| 用途 | 路径 |
| --- | --- |
| 应用入口与生命周期 | app/main.py |
| 本地启动 | run.py |
| 路由聚合 | app/api/v1/__init__.py |
| 配置中心 | app/core/config.py、.env.example |
| Agent 图装配 | app/agent/graph.py |
| 工具定义与治理 | app/agent/tools.py、app/agent/registry.py |
| Agent Profile 加载与校验 | app/agent/profiles.py、app/agents/*.yaml、app/agent/prompts/*.md |
| 评测脚手架入口 | evals/__main__.py（`python -m evals --fake` / `--real`） |
| MCP 接入（可选） | app/agent/mcp.py（网关聚合端点，Server 清单在 deploy/litellm/config.yaml） |
| 生命周期钩子（可选） | app/agent/hooks.py（`AGENT__HOOKS_MODULES` 声明注册模块） |
| 记忆策略（可选） | app/agent/memory.py（`AGENT__SUMMARY_ENABLED` 控制短期摘要；长期记忆默认 NoopMemory） |
| 可选 RAG（默认关闭） | app/rag/*（`RAG__ENABLED` 控制检索；引用经 `citations` SSE 事件返回） |
| 回合编排（偏好/RAG/工具事件/落库） | app/services/turn.py（路由只做 SSE 传输） |
| 异步任务接口（无 HTTP 路由） | app/services/task_runner.py（`TaskRunner` 协议 + 默认 `InlineTaskRunner`；调用方走 `get_task_runner()`，接入方用 `set_task_runner()` 替换） |

## 目录职责
| 目录 | 放什么 | 不放什么 |
| --- | --- | --- |
| app/api/v1 | 路由、鉴权依赖、参数校验、SSE 编码 | SQL、模型客户端创建、业务规则 |
| app/agent | 图结构、状态、提示词、工具、checkpointer | HTTP 请求处理 |
| app/services | LLM、会话存储、控制面、模型解析、用量上报 | 依赖 app/api |
| app/core | 配置、日志、异常、鉴权、中间件、指标 | 业务模块 |
| evals | YAML 评测用例、假/真模型 runner、报告 | 运行时业务逻辑 |
| scripts | 运维脚本（如数据回填） | 运行时业务逻辑 |
| tests | 单元与集成测试 | 生产代码 |

## 常见改动落点
| 需求 | 落点 |
| --- | --- |
| 新增一个 API 端点 | app/api/v1/<模块>.py、app/api/v1/__init__.py |
| 新增一个 Agent 工具 | app/agent/tools_ext/<模块>.py（或 AGENT__TOOL_MODULES 声明的模块）、tests/test_tool_registry.py |
| 新增一个 Agent Profile | app/agents/<id>.yaml（+ app/agent/prompts/<名称>.md）、tests/test_profiles.py |
| 修改工具治理（超时/重试/权限/配额/脱敏/截断） | app/agent/registry.py、app/agent/context.py、app/agent/tool_context.py、tests/test_tool_governance.py |
| 接入或排查 MCP Server | deploy/litellm/config.yaml（`mcp_servers`）、app/agent/mcp.py、tests/test_mcp.py（默认 `MCP__ENABLED=false`） |
| 新增审核/审计/可观测钩子 | app/agent/hooks.py、tests/test_hooks.py（默认零钩子；模块经 `AGENT__HOOKS_MODULES` 声明） |
| 调整长会话摘要/长期记忆 | app/agent/memory.py、app/agent/context.py、tests/test_memory.py（默认关闭；摘要不落库） |
| 接入或排查 RAG 检索 | app/rag/base.py、app/rag/registry.py、app/services/turn.py、tests/test_rag.py（默认 `RAG__ENABLED=false`，权限过滤须在检索前） |
| 接入长任务 / 队列 | app/services/task_runner.py、tests/test_task_runner.py（默认内联同步执行；不改路由，用 `set_task_runner()` 替换实现，处理器按 `kind` 注册） |
| 修改图节点或提示词 | app/agent/graph.py、app/agent/prompts.py、app/agent/state.py |
| 新增或修改会话持久化字段 | app/services/session_store/postgres.py（SQL 内嵌，须参数化） |
| 修改 LLM 调用或模型解析 | app/services/llm.py、app/services/model_resolver.py、app/services/model_runtime.py |
| 调整模型出口 | app/services/llm.py、deploy/litellm/config.yaml（ADR 0008：统一走 LiteLLM） |
| 修改鉴权 | app/core/security.py、app/api/v1/auth.py |
| 修改用量上报 | app/services/model_usage.py、app/services/usage_outbox.py |
| 新增一条评测用例 | evals/cases/<文件>.yaml（只改 YAML）、tests/test_evals.py |

## 测试
测试位于 tests/（test_*.py 与 conftest.py），命令 `uv --directory agent-service run pytest -q --cov=app --cov-report=term-missing`。
评测位于 evals/，命令 `uv --directory agent-service run python -m evals --fake`（CI 用，零 API 费用）。
