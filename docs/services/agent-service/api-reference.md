# Agent 端接口参考

| 项 | 内容 |
| --- | --- |
| 状态 | 已验证（源码级） |
| 基线 | 分支 `fix/post-refactor-bugfix`，HEAD `397b1fb`，含未提交改动 |
| 最后核验 | 2026-11-01 |
| 主要证据 | `agent-service/app/api/v1/{chat,sse,sessions,health,auth}.py`、`app/core/{exceptions,security,middleware}.py`、`app/services/{session_store,session_model,control_plane}.py` |

## 权威文档导航

| 主题 | 权威文档 |
| --- | --- |
| 全仓文档入口 | [docs/README.md](../../README.md) |
| 系统架构、服务边界、通信链路 | [docs/architecture-overview.md](../../architecture-overview.md) |
| 对外 HTTP / SSE 契约、错误码映射 | [docs/api-contract.md](../../api-contract.md)（Agent 端点 §6、SSE §7、模型错误码 §8） |
| Agent 分层、生命周期、数据归属 | [architecture.md](./architecture.md) |
| Agent 图结构、裁剪、工具治理、时序 | [agent-workflows.md](./agent-workflows.md) |
| 环境变量（唯一定义与默认值来源） | [docs/deployment/environment-variables.md](../../deployment/environment-variables.md) |
| Agent 编码硬约束 | [.trae/rules-on-demand/30-agent-python.md](../../../.trae/rules-on-demand/30-agent-python.md) |

本文只记录本服务的实现细节与行为；字段级契约以 `docs/api-contract.md` 为准，二者冲突时以代码为最终事实。

## 1. 通用约定

- 前缀：`API_PREFIX` = `/api/v1`；Nginx 把 `/agent/` 去前缀后转发，公网实际路径是 `/agent/api/v1/**`。
- 环境变量：本文出现的变量名（如 `METRICS__TOKEN`、`MODEL_RUNTIME__ENABLED`）只用于解释行为；完整清单、默认值与生产 fail-fast 规则统一见 [docs/deployment/environment-variables.md](../../deployment/environment-variables.md)，不在本文重复。
- 鉴权：除健康检查、指标与开发令牌外，全部要求 `Authorization: Bearer <token>`；令牌由 Java 用 RS256 私钥签发，Agent 只持公钥验签，按 `kid` 选钥并强制校验 `exp` / `sub` / `iss` / `aud` / `token_use="access"`；`sub` 是 Java 的 `users.public_id`（UUID）。
- 请求 ID：入站 `X-Request-ID` 若存在则复用，否则生成 uuid4 hex；响应头回传同名字段，并绑定到该请求的全部结构化日志。
- 错误信封：`{"code", "message", "request_id", "details"?}`，`details` 仅校验失败时出现。
- **成功响应没有信封**：直接返回业务对象（如会话列表、健康状态），与 Java 的 `{code, message, data, requestId}` **不同**，跨端复用解析逻辑时必须区分。
- 时间字段：ISO-8601 UTC，末尾 `Z`（如 `2026-10-28T12:00:00Z`）。
- 分页：`page` 从 1 开始，`size` 默认 20、上限 100；越界由路由显式校验返回 **400** `invalid_pagination`（与 Java 同一语义，不使用框架默认 422）。

## 2. 接口清单

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/v1/chat/stream` | 需要 | SSE 流式对话 |
| GET | `/api/v1/sessions` | 需要 | 当前用户会话列表（Postgres `session_meta`，含标题、`model_key`、置顶与归档状态） |
| PATCH | `/api/v1/sessions/{thread_id}` | 需要 | 重命名会话 |
| PUT | `/api/v1/sessions/{thread_id}/pin` | 需要 | 置顶/取消置顶 |
| PUT | `/api/v1/sessions/{thread_id}/archive` | 需要 | 归档/恢复 |
| PUT | `/api/v1/sessions/{thread_id}/model` | 需要 | 设置会话级模型，`model_key=null` 表示 Auto |
| DELETE | `/api/v1/sessions/{thread_id}` | 需要 | 删除会话（元数据 + 消息 + checkpoint） |
| GET | `/api/v1/sessions/{thread_id}/messages` | 需要 | 指定会话的历史消息（支持 `order=asc\|desc`） |
| GET | `/api/v1/health` | 无 | 存活检查（兼容旧路径，与 `health/live` 同一处理函数） |
| GET | `/api/v1/health/live` | 无 | 存活检查 |
| GET | `/api/v1/health/ready` | 无 | 就绪检查，依赖不满足时 503 |
| GET | `/api/v1/metrics` | 网关白名单 | Prometheus 文本，**不进 OpenAPI 文档**；配置 `METRICS__TOKEN` 时还需 `X-Metrics-Token` |
| POST | `/api/v1/auth/dev-token` | 无 | 仅 `APP_ENV=dev` 且 `DEBUG=true` 可用 |

登记在 `app/api/v1/__init__.py` 的路由共 **11 条**：上表 10 个操作 + 1 条兼容别名（`/health` 与 `/health/live` 由同一函数的两个装饰器注册）；`/metrics` 因 `include_in_schema=False` 不出现在 OpenAPI。

## 3. `POST /api/v1/chat/stream`

请求体：

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `message` | string | 1–4000 | 用户输入 |
| `thread_id` | string | 1–64 | **客户端自己的会话标识**；服务端内部拼成 `user_id:thread_id` |
| `model` | string \| null | ≤64，`^[a-z0-9][a-z0-9:_.-]*$`，可省略 | 单次覆盖本轮的模型；`null`/省略表示沿用会话选择或 Auto。仅 `MODEL_RUNTIME__ENABLED=true` 时生效 |
| `preferences` | object \| null | 可省略 | 客户端声明的用户偏好；只影响本轮提示词与历史注入，**不参与鉴权** |
| `preferences.instructions` | string \| null | ≤1000 | 追加到系统提示词的自定义指令；空白按未设置处理 |
| `preferences.reply_language` | string | `auto` / `zh-CN` / `en-US` | `auto` 不追加任何语言约束 |
| `preferences.response_style` | string | `concise` / `balanced` / `detailed` | 追加回答风格提示 |
| `preferences.use_history` | boolean | 默认 `true` | `false` 时模型只看本轮消息，但本轮仍正常落库 |
| `regenerate` | boolean | 默认 `false` | 为 `true` 时移除最后一条 AI 回答后重跑模型，并覆盖落库，不追加重复提问 |
| `reasoning` | boolean \| null | 可省略 | `true` 要求本轮开启思考；按 `model-tasks` 返回的 `capabilities` 校验，缺 `reasoning` 能力位返回 422 `capability_unsupported`。`null` 沿用模型默认行为；运行时关闭时忽略 |

`preferences` 省略时等价于全部默认值（不追加提示、注入历史）。服务端把偏好渲染成追加到系统提示词的片段，并按「基础提示词 + 偏好片段」重新计算上下文预算；`use_history=false` 时只取最后一条用户消息及其之后的窗口，状态与业务表仍保留完整历史。

可选请求头：

| 头 | 约束 | 行为 |
| --- | --- | --- |
| `Idempotency-Key` | 8–128 字符 | 幂等记录按用户隔离；重复提交返回 409。未启用 Redis 时该头被忽略 |

响应：`200` + `text/event-stream`，响应头带 `Cache-Control: no-cache`、`X-Accel-Buffering: no`。

**在返回流之前**可能失败（此时仍是普通 JSON 错误，可带正确状态码）：

| 状态 | code | 触发条件 |
| --- | --- | --- |
| 401 | `unauthorized` | 缺少 `Authorization` |
| 401 | `token_expired` / `token_invalid` | 令牌过期、签名/`kid`/issuer/audience/`sub`/`token_use` 任一不合法 |
| 409 | `duplicate_request` | 相同 `Idempotency-Key` 已成功处理 |
| 409 | `request_in_progress` | 相同 `Idempotency-Key` 正在处理 |
| 409 | `lock_not_acquired` | 同一会话正在生成，等待窗口（默认 3s）内没抢到锁 |
| 422 | `validation_error` | 请求体或头不满足约束 |
| 422 | `capability_unsupported` | `reasoning=true` 但当前模型目录未声明 `reasoning` 能力位；在流建立前返回，且不消耗 BYOK 一次性凭证 |
| 503 | `redis_unavailable` | 配置了 Redis 但客户端不可用 |

**流开始后** HTTP 状态固定为 200，此后只能通过事件表达结果：

| 事件 | data | 说明 |
| --- | --- | --- |
| `token` | `{"text": "..."}` | 模型输出的文本增量 |
| `reasoning` | `{"text": "..."}` | 思考内容增量；由网关归一化 `reasoning_content` 后下发，与正文分离，仅部分模型提供 |
| `tool_call` | `{"name": "...", "args": {...}}` | 模型发起工具调用（来自 `model` 节点） |
| `tool_result` | `{"name": "...", "preview": "前 200 字符"}` | 工具返回 |
| `done` | `{"thread_id": "客户端原值"}`，PC 配置成功时额外带可选 `build_result` | 正常结束；回传客户端 ID，不暴露服务端命名空间 |
| `error` | `{"code": "request_timeout" \| "agent_error", "message": "..."}` | 超时或内部错误 |

编码格式（每个事件以空行结束）：

```
id: 3
event: token
data: {"text": "你好", "schema_version": "1"}
```

- 每个事件的 `data` 都带 `schema_version`（当前 `"1"`），由编码层统一注入；新增字段一律可选，旧前端忽略后仍可渲染。
- `done.build_result` 仅在 PC 流水线成功且存在配置时出现，字段见 [api-contract.md](../../api-contract.md) §7；缺失时前端回退 Markdown 正文。默认 Profile 为 `pc-config`，见 [docs/pc-config/agent-workflow.md](../../pc-config/agent-workflow.md)。
- `id` 从 1 自增，仅用于排查乱序，**不做断点续传**。
- 心跳为注释行 `: ping\n\n`，由 sse-starlette 的 `EventSourceResponse(ping=...)` 实现，默认每 15s 一次（`AGENT__SSE_HEARTBEAT_SECONDS`），前端必须忽略注释。
- 分隔符统一为 LF（`\n`），事件块以空行结束；`Content-Type` 为 `text/event-stream; charset=utf-8`。
- 整轮超时（默认 120s）触发 `error` + `request_timeout`；客户端断开时服务端取消图执行、不产生 `done`。
- 生成结束后先落库与发送 `done`，再释放会话锁与幂等记录；收尾失败只记 warning，不影响已发出的流。

## 4. `GET /api/v1/sessions`

Query：`page`（≥1，默认 1）、`size`（1–100，默认 20）、`archived`（默认 `false`）。

```json
{
  "list": [
    {
      "thread_id": "my-thread",
      "title": "现在几点",
      "model_key": "deepseek:deepseek-v4-pro",
      "last_active_at": "2026-10-28T12:00:00Z",
      "is_pinned": true,
      "is_archived": false
    }
  ],
  "total": 1,
  "page": 1,
  "size": 20
}
```

- 数据来源是 Postgres 表 `session_meta`（2026-10-29 起，`app/services/session_store/postgres.py`），按 `is_pinned DESC, last_active_at DESC, thread_id` 返回；`archived` 控制是否查看归档列表；本机/测试用进程内适配器。
- Redis 未配置时列表照常可用；历史上「依赖 Redis 索引、未启用返回 503」的行为已取消。
- 每轮对话写入 `session_messages` 的同一处 upsert 元数据；`title` 取首条用户消息前 40 个字符，尚未生成时为 `null`。
- `model_key` 是该会话的模型选择，`null` 表示 Auto；写入入口只有 §5.2 的 `PUT /sessions/{thread_id}/model`。
- 旧的 `AGENT__SESSION_INDEX_TTL_SECONDS` / `AGENT__SESSION_INDEX_MAX` 已废弃（`app/core/config.py` 中标记 `deprecated=True`，仅为兼容旧部署保留键名）；变量权威定义见 [docs/deployment/environment-variables.md](../../deployment/environment-variables.md)。
- 历史会话回填：`python scripts/backfill_session_meta.py --dry-run` 预览，去掉参数后写入；脚本幂等，已存在的会话不覆盖。

## 5. 会话历史、模型设置、置顶归档、重命名与删除

### 5.1 `GET /api/v1/sessions/{thread_id}/messages`

Path：`thread_id`（1–64）；Query 同 §4，另有 `order`（`asc` 默认 / `desc`）。

```json
{
  "thread_id": "my-thread",
  "list": [
    { "role": "user", "content": "现在几点", "created_at": "2026-11-06T08:00:00Z" },
    { "role": "assistant", "content": "", "tool_calls": [{ "name": "get_current_time", "args": {} }], "created_at": "2026-11-06T08:00:01Z" },
    { "role": "tool", "content": "...", "name": "get_current_time", "created_at": "2026-11-06T08:00:02Z" },
    { "role": "assistant", "content": "现在是……", "created_at": "2026-11-06T08:00:03Z" }
  ],
  "total": 4,
  "page": 1,
  "size": 20,
  "order": "asc"
}
```

- 数据来源是 `session_messages` 表（每轮生成结束时写入），不读 checkpointer，也不依赖 Redis，所以 **Redis 不可用时该接口仍可用**。
- 归属隔离靠查询条件里的 `user_id`：`thread_id` 保持客户端原值，服务端按 (`user_id`, `thread_id`) 组合存储与查询，伪造 ID 只会得到自己名下的空结果。
- 分页在数据库侧完成（`ORDER BY seq LIMIT/OFFSET` + `COUNT`），读取量只与页大小有关，与历史长度无关；`total` 是该会话消息总数。
- `order=desc` 时按 `seq` 倒序返回窗口，供长会话从最新一页向前翻；响应中的 `order` 回显请求值。
- 无任何消息时返回 404 `session_not_found`（`会话不存在或尚无消息`）。
- `role` 取值：`user` / `assistant` / `tool` / `system` / `unknown`；非字符串内容会被 JSON 序列化后放入 `content`；`created_at` 为落库时间，用于前端消息时间展示。
- 写入时机：每轮结束**先落库再发 `done`**，前端收到 `done` 后立即查询即可看到本轮消息；落库失败只记 warning，不阻断对话（该轮历史会缺失）。

### 5.2 `PUT /api/v1/sessions/{thread_id}/model`

设置会话级模型；`model_key=null` 恢复 Auto。字段与错误码的完整契约见 `docs/api-contract.md` §6，这里只记录本服务的实现要点。

Path：`thread_id`（1–64）。

请求体：

```json
{ "model_key": "deepseek:deepseek-v4-pro" }
```

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `model_key` | string \| null | ≤64，`^[a-z0-9][a-z0-9:_.-]*$`，可省略 | `null` 或省略表示 Auto（平台默认模型） |

响应 `200`：

```json
{
  "thread_id": "my-thread",
  "model_key": "deepseek:deepseek-v4-pro",
  "effective": "explicit",
  "model": {
    "provider": "deepseek",
    "model_key": "deepseek:deepseek-v4-pro",
    "display_name": "GPT-4o mini",
    "capabilities": ["text", "tool_calling"],
    "context_window": 128000
  },
  "updated_at": "2026-10-30T08:00:00Z"
}
```

- 编排入口是 `app/services/session_model.py` 的 `set_session_model`；路由只做参数接收与响应组装。
- 校验顺序固定为「会话归属 → 目录与用户可用性 → 写库」，任一步失败都不写库（`app/services/session_model.py` 的注释即此约束）。
- `effective` 为 `explicit` / `auto`，由响应组装层按 `model_key` 是否为 `null` 计算；`auto` 时 `model` 为 `null`、`updated_at` 可以是已有记录的时间。
- 幂等：重复提交相同 `model_key` 不改 `updated_at`；恢复 Auto 且原本就是 Auto 时同样不写库。
- 只有显式 `model_key` 才校验 `MODEL_RUNTIME__ENABLED` 并发起控制面调用；传 `null` 只改本地 `session_meta.model_key`，不访问 Java。
- 落库位置是 `session_meta.model_key`，写入同时刷新 `updated_at`；会话被并发删除时返回 404 而不是新建记录。
- 单次请求覆盖模型不走此接口，只由 `POST /chat/stream` 的 `model` 字段表达（见 §3 请求体）。

错误：

| 状态 | code | 触发条件 |
| --- | --- | --- |
| 401 | `unauthorized` | 缺少访问令牌（显式 `model_key` 需要令牌做可用性校验） |
| 404 | `session_not_found` | 会话不存在或不属于当前用户；写入时会话已被删除 |
| 422 | `validation_error` | `model_key` 格式或长度不合法 |
| 403 | `model_not_available` | 模型不在目录或当前用户不可用（Java `40202`） |
| 503 | `control_plane_unavailable` | 控制面不可达（Java 调用失败不做降级） |
| 503 | `model_runtime_disabled` | `MODEL_RUNTIME__ENABLED=false` 且请求了显式模型 |

控制面返回的其他业务码（`quota_exceeded`、`capability_unsupported` 等）原样透传，完整映射见 §8。

### 5.3 `PATCH /api/v1/sessions/{thread_id}`

Body：

```json
{ "title": "排查登录失败" }
```

- 标题在服务端去首尾空白后校验 1..80 字符；空白或超长返回 422 `validation_error`（`details` 指向 `title`）。
- 成功返回 `{ "thread_id": "...", "title": "排查登录失败" }`。
- 会话不存在或不属于当前用户返回 404 `session_not_found`，两种情况不区分，避免探测他人会话。

### 5.4 `PUT /api/v1/sessions/{thread_id}/pin` 与 `/archive`

Body 分别为 `{ "pinned": true }` 与 `{ "archived": true }`，返回：

```json
{ "thread_id": "my-thread", "is_pinned": true, "is_archived": false, "updated_at": "2026-11-06T08:00:00Z" }
```

- 置顶只影响排序；归档后从默认列表移除，`GET /sessions?archived=true` 可查询并恢复。
- 会话不存在或不属于当前用户返回 404 `session_not_found`。

### 5.5 `DELETE /api/v1/sessions/{thread_id}`

- 成功返回 **204**，无响应体；重复删除返回 404 `session_not_found`。
- 同时清理 `session_meta`、`session_messages`；该会话的 checkpointer 状态登记到 `session_deletion_tasks` 墓碑，由后台按退避重试删除，失败可在表中与 `agent_session_deletion_tasks` 指标上追踪，不改变 204。
- 墓碑入队失败（数据库不可用）时退回一次性尽力删除，接口契约不变。
- 同一 `thread_id` 删除后重新发起对话会取消未执行的墓碑，避免误删新一轮检查点。
- 删除前抢会话锁（与生成共用），同一会话正在生成时返回 409 `lock_not_acquired`，避免删掉半轮消息。

## 6. 系统接口

### `GET /api/v1/health`、`GET /api/v1/health/live`

```json
{ "status": "ok", "env": "dev", "service": "agent-service", "redis": "disabled" }
```

`redis` 取值：`disabled`（未配置）/ `unavailable`（配置了但客户端未建立）/ `down`（PING 失败）/ `up`。

### `GET /api/v1/health/ready`

```json
{
  "status": "ready",
  "env": "dev",
  "service": "agent-service",
  "dependencies": { "checkpointer": "postgres", "redis": "disabled" }
}
```

判定规则：

- checkpointer 必须是 `up` 或 `memory`；**`prod` 下 `memory` 直接判为不就绪**。
- 配置了 Redis 时必须为 `up`；未配置时必须为 `disabled`。
- 任一不满足返回 **503**，`status` 为 `not_ready`，但响应体结构不变。

### `GET /api/v1/metrics`

- 返回 Prometheus 文本格式，`METRICS__ENABLED=false` 时返回 404 `metrics_disabled`（开关默认值与生产要求见 [docs/deployment/environment-variables.md](../../deployment/environment-variables.md)）。
- 鉴权分层：**Nginx 白名单为主防线**（精确 location 只放行回环与私有网段），应用内 `METRICS__TOKEN` 为兜底；配置了该变量后必须携带 `X-Metrics-Token`，缺失或不匹配返回 403 `metrics_forbidden`。
- 共 13 个指标族：HTTP 请求数/耗时、SSE 活跃流/首 token 延迟/超时/断开、工具调用结果/重试、LLM token 用量、用量 outbox 待投递数（`agent_usage_outbox_pending`）、outbox 终态数（`agent_usage_outbox_dead`）、outbox 降级次数（`agent_usage_outbox_degraded_total`）、会话删除墓碑按状态（`agent_session_deletion_tasks{status}`）；**不把 `user_id` / `thread_id` 作为标签**。

## 7. `POST /api/v1/auth/dev-token`

> 仅用于本地联调，**不属于生产契约**。

请求：`{"user_id": "...", "expires_minutes": 60}`（`user_id` 1–64，`expires_minutes` 1–1440）。

响应：`{"access_token": "...", "token_type": "Bearer", "expires_in": 3600}`。

- 守卫条件：`APP_ENV=dev` **且** `DEBUG=true`，否则 403 `forbidden`（环境变量权威定义见 [docs/deployment/environment-variables.md](../../deployment/environment-variables.md)）。
- 签发的 claims 为 `sub` / `iss` / `aud` / `roles=["user"]` / `iat` / `exp` / `jti` / `token_use="access"`；`aud` 由 `AUTH__AUDIENCE` 提供且必填（默认 `agent-clients`），不是可选字段。
- 大小写统一为 `Bearer`，与 Java 签发方一致（2026-10-28 已修正）。

## 8. 错误码总表

| code | HTTP | 来源 | 说明 |
| --- | --- | --- | --- |
| `unauthorized` | 401 | `security.py` | 缺少访问令牌 |
| `token_expired` | 401 | `security.py` | `exp` 已过期 |
| `token_invalid` | 401 | `security.py` | 签名 / `kid` / 算法 / issuer / audience / `sub` / `token_use` 任一不合法 |
| `forbidden` | 403 | `auth.py` | 生产环境调用开发令牌接口 |
| `session_not_found` | 404 | `sessions.py` / `session_model.py` | 会话无消息，或重命名/删除/设置模型的会话不归属当前用户 |
| `invalid_pagination` | 400 | `sessions.py` | 分页越界：`page < 1` 或 `size` 不在 1..100 |
| `duplicate_request` | 409 | `chat.py` | 幂等键已成功处理 |
| `request_in_progress` | 409 | `chat.py` | 幂等键正在处理 |
| `lock_not_acquired` | 409 | `lock.py` | 同一会话并发（生成或删除），等待窗口内未抢到锁 |
| `app_error` | 400（默认） | `exceptions.py` | `AppError` 未显式指定时的兜底 code |
| `validation_error` | 422 | `exceptions.py` | 请求参数校验失败，带 `details[].field` / `details[].reason` |
| `http_{status}` | 原样 | `exceptions.py` | 框架级 404/405 等，如 `http_404` |
| `internal_error` | 500 | `exceptions.py` | 未捕获异常；`DEBUG=false` 时消息固定为「服务器内部错误」 |
| `redis_unavailable` | 503 | `exceptions.py` | Redis 已配置但不可用（会话锁、幂等键）；会话列表/历史不依赖 Redis |
| `metrics_disabled` | 404 | `health.py` | 指标端点被关闭 |
| `metrics_forbidden` | 403 | `health.py` | 已配置 `METRICS__TOKEN`，请求未带或带错 `X-Metrics-Token` |
| `request_timeout` | —（SSE `error` 事件） | `chat.py` | 流内超时，HTTP 已固定为 200 |
| `agent_error` | —（SSE `error` 事件） | `chat.py` | 流内未预期异常 |
| `quota_exceeded` | 429 | `control_plane.py` | 每日请求额度用尽（Java `40201` 透传）；BYOK 同样计入 |
| `model_not_available` | 403 | `control_plane.py` | 模型不在目录或当前用户不可用（Java `40202`） |
| `capability_unsupported` | 422 | `control_plane.py` | 模型能力不满足本次请求（Java `40203`） |
| `control_plane_unavailable` | 503 | `control_plane.py` | 控制面不可达或网络失败，显式模型请求不降级 |
| `credential_revoked` | 401 | `control_plane.py` | BYOK 凭证已撤销/删除/用户被禁用（Java `40216`），需重新配置 |
| `credential_lease_consumed` | 409 | `control_plane.py` | 任务凭证已被兑换过（Java `40215`，严格一次性） |
| `lease_not_byok` | 409 | `control_plane.py` | 对 MANAGED 任务发起凭证兑换（Java `40218`） |
| `credential_rejected` | 422 | `control_plane.py` | 显式模型未通过可用性校验或凭证被上游拒绝（Java `40219`） |
| `credential_unavailable` | 503 | `llm.py` | 请求 BYOK 但无法取得可用凭证（未配置连接/兑换失败） |
| `upstream_error` | 503 | `control_plane.py` | 上游 Provider 返回错误或未知 Java 错误码（Java `40217` 归入此码） |
| `llm_not_configured` | 503 | `llm.py` | 未配置 `LLM__GATEWAY_API_KEY`（或直连模式下的 `LLM__API_KEY`），或密钥仍是占位符 |
| `llm_provider_unsupported` | 422 | `llm.py` | BYOK 场景下 provider 无法映射到网关前缀（仅支持 openai / deepseek / qwen / volcengine / gemini / anthropic） |
| `model_runtime_disabled` | 503 | `session_model.py` | `MODEL_RUNTIME__ENABLED=false` 且请求了显式会话模型 |
| `dev_token_unavailable` | 503 | `auth.py` | dev 环境未配置 `AUTH__DEV_PRIVATE_KEY`，开发令牌无法签发（生产环境改为 403 `forbidden`） |

> 模型运行时的完整码表与 Java 数字码映射见根 `docs/api-contract.md` §8；`byok_unsupported` 已随 PR5 移除，不再使用。

## 9. 与 Java 端的契约差异（避免误用）

| 维度 | Java `application-service` | Agent `agent-service` |
| --- | --- | --- |
| 成功响应 | 信封 `{code:0, message, data, requestId}` | 裸对象 |
| 错误响应 | `{code: 数字, message, data?, requestId}` | `{code: 字符串, message, request_id, details?}` |
| 请求 ID 头 | `X-Request-Id`（正则白名单，非法则替换） | `x-request-id`（任意值直接复用，不校验格式） |
| 校验失败 | 400 + `FieldViolation` 列表 | 422 + `details[].field/reason` |
| 时间格式 | ISO-8601 UTC | ISO-8601 UTC（一致） |
| 分页 | `page`/`size`，`size ≤ 100` 越界 400 | `page`/`size`，默认 20、上限 100，越界 400 `invalid_pagination`（一致） |

这两套信封的差异是**当前实现的真实状态**，未做统一；跨端封装必须分别适配，不能共用同一个解析器。
