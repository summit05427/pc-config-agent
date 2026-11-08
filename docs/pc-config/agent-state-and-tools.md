# PC 配置状态、工具与 Profile

| 项 | 内容 |
| --- | --- |
| 状态 | 已验证（与 `PCConfigState` 及工具注册表一致） |
| 最后核验 | 2026-11-08 |
| 权威性 | 本文件描述图状态、checkpointer、工具治理与 Profile 的真实配置；环境变量默认值以[环境变量文档](../deployment/environment-variables.md)为准 |
| 主要证据 | `app/agent/pc/state.py`、`tools.py`、`app/agent/registry.py`、`app/agent/checkpointer.py`、`app/agents/pc-config.yaml` |

## 1. PCConfigState 字段

| 字段 | 用途 | 是否持久化 |
| --- | --- | --- |
| `messages` | 用户输入与最终 AI 正文；`turn.py` 依赖它落库 | checkpointer + `session_messages` |
| `preference_prompt` | 本轮偏好片段，由 `turn.py` 每轮显式写入 | 仅 checkpointer，不写业务表 |
| `use_history` | 是否向模型注入历史；每轮覆盖 | 仅 checkpointer，不写业务表 |
| `requirements` | 结构化需求（`PCRequirements.model_dump()`） | 仅 checkpointer |
| `validation_result` | 校验状态、追问文案与缺失字段 | 仅 checkpointer |
| `candidate_pool` | 8 类候选计数、目录版本、缺失类别、跑分与报价统计 | 仅 checkpointer |
| `build_result` | Java 求解返回的结构化配置 | 仅 checkpointer |
| `build_failure` | 无解原因、最低可行预算与缺失类别 | 仅 checkpointer |
| `compatibility_report` | 兼容性总状态与逐条检查 | 仅 checkpointer |
| `budget_report` | 预算上限、总价与预算状态 | 仅 checkpointer |
| `reason_summary` | 最终推荐说明（LLM 或确定性文案） | 仅 checkpointer |
| `retry_count` | 已发生的重解次数 | 仅 checkpointer |
| `workflow_status` | 路由与失败分支的唯一依据 | 仅 checkpointer |
| `tool_events` | 节点累积的工具进度，由 `turn.py` 消费 | 仅 checkpointer |

状态中不保存用户令牌、服务令牌、完整 JWT 或全量商品列表；`user_token` 只存在于 `TurnRequest`。

## 2. checkpointer 行为

- 默认 `MemorySaver`，仅测试 / 本地；`STORAGE__BACKEND=postgres` 时使用 `AsyncPostgresSaver` 与 `psycopg_pool` 连接池。
- 连接池必须 `autocommit=True`：`setup()` 含 `CREATE INDEX CONCURRENTLY`，不能在事务块执行。
- `STORAGE__AUTO_SETUP=true` 时启动即幂等建表；退出时关闭连接池并回退 `MemorySaver`。
- 图编译时注入当前 checkpointer；切换实现会清除已缓存的图，避免继续使用旧存储。
- `thread_id` 用命名空间值（`user_id:客户端值`）；`session_messages` 只写客户端原始值，两者不能混用。
- `turn.py` 在流结束后用 `aget_state` 读取最终状态，先落库再发 `done`。

## 3. 五个工具

| 工具 | 参数 | 上游 / 用途 | 超时 | 输出上限 | 单轮配额 |
| --- | --- | --- | --- | --- | --- |
| `search_hardware_candidates` | `category?` | `GET /internal/v1/pc/hardware/candidates` | 10s | 4000 | 12 |
| `get_benchmark_data` | `hardware_id?`、`category?` | `GET /internal/v1/pc/benchmarks` | 10s | 4000 | 12 |
| `get_verified_offers` | `hardware_id?`、`category?`、`verified_only=false` | `GET /internal/v1/pc/offers` | 10s | 6000 | 12 |
| `solve_pc_build` | `budget_max_fen?`、`scenario`、`min_memory_gb?`、`min_storage_gb?`、`require_verified_offers` | `POST /internal/v1/pc/builds/solve` | 25s | 8000 | 3 |
| `validate_pc_build` | `cpu`、`motherboard`、`memory`、`gpu`、`psu`、`case`、`cooler`、`storage`（均必填） | `POST /internal/v1/pc/builds/validate` | 10s | 4000 | 3 |

- 重试次数未在工具注册时覆盖，统一取 `AGENT__TOOL_MAX_RETRIES`（默认 1）；只有真正重跑才计重试指标。
- 输出先转文本，再按 `AGENT__TOOL_REDACT_OUTPUT`（默认 `true`）脱敏手机号、邮箱、身份证、API Key 与 Bearer，再按 token 预算截断并追加提示。
- 单轮配额由 `ToolTurn` 的 `ContextVar` 累计；超限返回提示文本而非抛错。
- `solve_pc_build` 标记 `is_read_only=false`，且必须携带 `X-User-Token`；缺少身份时返回「请重新登录」安全错误。
- 工具异常统一包成 `ToolExecutionError`，内部地址与堆栈只进日志；`get_verified_offers` 默认允许返回 `MOCK_DEMO`，由渲染层强制标注。
- 节点只通过 `get_governed_tool(name)` 取工具，禁止直接使用 `httpx`。

## 4. Profile 配置

| 字段 | 值 |
| --- | --- |
| `id` | `pc-config` |
| `display_name` | PC 配置推荐 |
| `system_prompt` | `pc-config-system` |
| `model.temperature` | `0.3` |
| `model.max_tokens` | `2048` |
| `tools` | 上述 5 个工具的完整列表 |
| 默认 Profile | `AGENT__DEFAULT_PROFILE=pc-config`（代码 `config.py`；环境变量文档默认值列仍写 `default`，以代码为准，待 Stage 6.5 同步） |

- Profile 的 `extra="forbid"`，不能选择图；单图由 `build_agent` 固定装配。
- Profile 校验在启动期完成；提示词缺失、工具未注册或 id 与文件名不一致都会拒绝启动。

## 5. Prompt 文件职责

| 文件 | 职责 | 约束 |
| --- | --- | --- |
| `pc-config-system.md` | 系统人格与硬性规则 | 型号、价格、链接只来自结构化结果；`UNKNOWN` 不得说通过；演示价必须标注 |
| `requirement-parser.md` | 把用户消息解析为唯一 JSON 对象 | 只输出 JSON；金额为整数分；不猜测未提供的预算、容量或用途 |
| `response-generator.md` | 生成 2–3 句推荐说明 | 禁止数字、金额、型号、品牌、SKU、链接与渠道；不复述组件清单 |

- 三个文件位于 `app/agent/prompts/`，由 `load_prompt` 在构图时加载。
- 解析与生成调用均打 `TAG_NOSTREAM`，内部 JSON 与说明不会以流式 `token` 泄漏。
