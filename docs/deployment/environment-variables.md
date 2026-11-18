# 环境变量参考

| 项 | 内容 |
| --- | --- |
| 适用范围 | 根 `.env`、`agent-service/.env`、Compose 注入与生产 fail-fast |
| 状态 | Authoritative（环境变量唯一权威） |
| 最后更新 | 2026-11-17 |
| 主要证据 | 根 `.env.example`、`agent-service/.env.example`、`docker-compose.yml`、各端校验器 |

## 1. 结论先行

- 根 `.env` 供 Compose 与宿主机四端共用；Agent 的嵌套变量在 `agent-service/.env.example`。
- 真实 `.env` 不提交；生产必须替换全部 `replace-with-*`，否则 `ProdConfigGuard` / `Settings` 拒绝启动。
- 模型默认 `deepseek:deepseek-flash`：根 `MODEL_DEFAULT_KEY` 与 `LLM_MODEL`、网关 `model_name` 必须同名。
- `VITE_*` 会打进静态产物，禁止放密钥；改 `VITE_*` 或源码必须重建前端镜像。
- 只改数据库、JWT、LLM 等运行时变量不需要重建镜像，重启对应进程即可。

## 2. 变量分组

### 2.1 Compose 与端口

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `COMPOSE_PROJECT_NAME` | `pc-config-advisor` | 决定容器、数据卷与网络前缀；多项目并行必须唯一 |
| `IMAGE_PREFIX` | `pc-config-advisor` | 本地镜像 tag 前缀 |
| `WEB_BIND` | `0.0.0.0` | 前端容器在宿主机上的监听地址。服务器前置 Nginx 时必须设为 `127.0.0.1`，因为 Docker 发布端口绕过 ufw |
| `WEB_PORT` | `8088` | 宿主机端口，映射 Nginx 80 |
| `BACKEND_PORT` / `AGENT_PORT` | `8080` / `8000` | Java / Agent 宿主机端口 |
| `POSTGRES_PORT` / `AGENT_POSTGRES_PORT` / `REDIS_PORT` | `15432` / `15433` / `16379` | 宿主机端口 |
| `SPRING_PROFILES_ACTIVE` | `prod` | `local` / `dev` / `test` / `prod`；生产强制 `prod` |
| `APP_ENV` | `prod` | Agent 环境，仅 `dev` / `staging` / `prod` |

### 2.2 数据库

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `agent` / 占位 / `agent` | Java 业务库 |
| `AGENT_POSTGRES_USER` / `AGENT_POSTGRES_PASSWORD` / `AGENT_POSTGRES_DB` | `agent` / 占位 / `agent_service` | Agent 会话库 + checkpointer |
| `REDIS_PASSWORD` | 占位 | 含 `@ : / #` 时必须 URL 编码 |

### 2.3 JWT、Refresh 与引导账号

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` | PEM | Java 持私钥，Agent 只用公钥；PEM 压成单行 `\n` |
| `JWT_KID` | `rsa-2026-10` | 写入 JWS Header，轮换时按 `kid` 选公钥 |
| `JWT_ISSUER` / `JWT_AUDIENCE` | `agent-application-service` / `agent-clients` | 两端必须一致 |
| `JWT_ACCESS_TTL` | `10m` | Access Token 有效期 |
| `AUTH_REFRESH_IDLE_TTL` / `AUTH_REFRESH_ABSOLUTE_TTL` | `7d` / `30d` | 刷新令牌闲置 / 绝对上限 |
| `AUTH_REFRESH_ROTATION_GRACE` | `60s` | 并发刷新宽限期 |
| `AUTH_COOKIE_SECURE` | `true` | 生产必须 `true`，否则拒绝启动 |
| `AUTH_ADMIN_USERNAME` / `AUTH_ADMIN_PASSWORD` / `AUTH_ADMIN_ROLES` | `admin` / 占位 / `ADMIN` | 首次启动创建；口令空则不创建 |
| `AUTH_DEMO_USERNAME` / `AUTH_DEMO_PASSWORD` / `AUTH_DEMO_ROLES` | `demo` / 空 / `USER` | 仅本地/预发建议启用 |
| `CORS_ALLOWED_ORIGINS` | 空 | 同源部署留空；分域时英文逗号分隔白名单，禁用 `*` |

### 2.4 模型运行时（Java）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `MODEL_RUNTIME_ENABLED` | `false` | 关闭时 `/internal/v1/**` 与 `/api/v1/models` 返回 404；部署模板默认 `true` |
| `BYOK_ENABLED` | `false` | 必须同时开启运行时总开关；部署模板默认 `true` |
| `MODEL_MANAGED_ENABLED` | `true` | 是否展示平台托管模型；纯 BYOK 部署模板默认 `false` |
| `MODEL_MANAGED_PROBE_TTL` | `30s` | 平台密钥可用性探测缓存 |
| `MODEL_CRED_MASTER_KEY` | 空 | BYOK 加密主密钥，32 字节 base64；只注入 Java |
| `MODEL_CRED_KEY_VERSION` | `1` | 新密文密钥版本 |
| `MODEL_CRED_MASTER_KEYS` | 空 | 多版本密钥环 `<version>:<base64>`，逗号分隔 |
| `MODEL_CRED_VERIFY_TIMEOUT` | `5s` | 凭证远程验证超时 |
| `MODEL_CRED_VERIFY_RATE_LIMIT_PER_MINUTE` | `5` | 单用户每分钟验证次数 |
| `MODEL_DEFAULT_KEY` | `deepseek:deepseek-flash` | Auto 默认模型，与网关 `model_name` 同名 |
| `MODEL_TASK_TTL` | `10m` | 运行时任务有效期与幂等窗口 |
| `MODEL_TASK_CLEANUP_ENABLED` / `MODEL_TASK_CLEANUP_CRON` | `true` / `0 0 * * * *` | 过期任务置 `EXPIRED`，不物理删除 |
| `MODEL_QUOTA_DAILY_REQUESTS` | `100` | 每用户每日请求额度 |
| `MODEL_RECONCILE_ENABLED` / `MODEL_RECONCILE_CRON` | `true` / `0 5 0 * * *` | 只读对账 |
| `INTERNAL_AUTH_CLIENT_ID` / `INTERNAL_AUTH_CLIENT_SECRET` | `agent-service` / 占位 | 服务令牌客户端；生产 secret ≥ 16 字符 |
| `INTERNAL_AUTH_TOKEN_TTL` | `5m` | 服务令牌有效期 |

### 2.5 LLM 与 LiteLLM 网关

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `LLM_MODEL` | `deepseek:deepseek-flash` | 模型标识即网关 `model_name` |
| `LLM__GATEWAY_BASE_URL` | `http://127.0.0.1:4000` | 宿主机直跑；容器内固定 `http://litellm:4000` |
| `LLM__GATEWAY_API_KEY` | 占位 | 必须等于 `LITELLM_MASTER_KEY`；为空退化为直连 |
| `LLM_GATEWAY_API_KEY` | 空 | 容器内覆盖；Solo 显式置空强制直连 |
| `LLM_API_KEY` / `LLM_BASE_URL` | 占位 / `https://api.deepseek.com/v1` | 直连模式专用 |
| `LLM_MAX_TOKENS` | `2048` | 单次生成上限 |
| `LITELLM_MASTER_KEY` | 占位 | 网关管理口令，仅 Agent 持有；生产 ≥ 32 字符 |
| `LITELLM_SALT_KEY` | 占位 | 网关加密盐，设置后不可更改 |
| `LITELLM_PORT` | `4000` | 仅绑定回环 |
| `MODEL_GATEWAY_BASE_URL` / `MODEL_GATEWAY_MASTER_KEY` | 本地回环 / 占位 | 宿主机直跑 Java 时使用 |
| `OPENAI_API_KEY` / `QWEN_API_KEY` / `VOLCENGINE_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` | 空 | 留空表示不启用该 provider |

### 2.6 Agent 运行参数（`agent-service/.env`）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `APP_NAME` / `API_PREFIX` / `DEBUG` | `agent-service` / `/api/v1` / `true` | 服务标识与路由前缀；Compose 固定 `DEBUG=false` |
| `LLM__MODEL` / `LLM__TEMPERATURE` / `LLM__MAX_TOKENS` / `LLM__TIMEOUT_SECONDS` | `deepseek:deepseek-flash` / `0.7` / `2048` / `60` | Agent 侧模型参数 |
| `LLM__API_KEY` / `LLM__BASE_URL` | 占位 / `https://api.deepseek.com/v1` | 直连模式 |
| `MODEL_RUNTIME__ENABLED` | `false` | 接 Java 模型控制面 |
| `CONTROL_PLANE__BASE_URL` / `CLIENT_ID` / `CLIENT_SECRET` / `TIMEOUT_SECONDS` | 内网地址 / `agent-service` / 占位 / `5` | 服务令牌换取 |
| `AUTH__JWT_PUBLIC_KEY` / `AUTH__JWT_ALGORITHM` / `AUTH__JWT_KID` / `AUTH__ISSUER` / `AUTH__AUDIENCE` | 公钥 / `RS256` / 同 `JWT_KID` / 同 `JWT_ISSUER` / 同 `JWT_AUDIENCE` | 只验签 |
| `AUTH__DEV_KID` / `AUTH__ACCESS_TOKEN_EXPIRE_MINUTES` | `rsa-dev` / `60` | 仅 dev + debug 的 dev-token 使用 |
| `STORAGE__BACKEND` | `memory` | `postgres` / `memory`；Compose 与本地 `.env` 均为 `postgres`，HITL 必须 `postgres` |
| `STORAGE__POSTGRES_URL` / `STORAGE__POOL_SIZE` / `STORAGE__AUTO_SETUP` | 内网 DSN / `5` / `true` | checkpointer 连接池 |
| `REDIS__REQUIRED` / `REDIS__MAX_CONNECTIONS` / `REDIS__LOCK_TTL_SECONDS` | `false` / `10` / `30` | 分布式锁与连接；Compose 强制 `REQUIRED=true` |
| `AGENT__CONTEXT_MAX_TOKENS` / `AGENT__RECURSION_LIMIT` / `AGENT__REQUEST_TIMEOUT_SECONDS` | `6000` / `12` / `120` | 上下文、递归与单轮超时 |
| `AGENT__THREAD_LOCK_TTL_SECONDS` / `AGENT__THREAD_LOCK_WAIT_SECONDS` | `300` / `3` | 同一线程并发保护 |
| `AGENT__SSE_HEARTBEAT_SECONDS` | `15` | SSE 心跳 |
| `AGENT__SYSTEM_PROMPT` / `AGENT__PROFILES_DIR` / `AGENT__DEFAULT_PROFILE` | `pc-config-system` / `app/agents` / `pc-config` | Profile 加载 |
| `AGENT__TOOL_TIMEOUT_SECONDS` / `TOOL_MAX_RETRIES` / `TOOL_MAX_OUTPUT_TOKENS` / `TOOL_MAX_CALLS_PER_TURN` | `10` / `1` / `2000` / `3` | 工具治理 |
| `AGENT__TOOL_REDACT_OUTPUT` | `true` | 工具输出脱敏 |
| `AGENT__ARCHITECT_MAX_PARTIAL_CHECKS` / `MAX_KNOWLEDGE_CALLS` / `MAX_TOKENS` | `4` / `2` / `4096` | `build_architect` 配额 |
| `AGENT__MULTI_AGENT_ENABLED` / `AGENT__CRITIC_ENABLED` | `true` / `true` | 多 Agent：默认开启；开启后 Specialist 并行分析、Critic 只评审不改方案 |
| `AGENT__SUMMARY_ENABLED` / `TRIGGER_TOKENS` | `false` / `5000` | 长会话摘要，默认关闭 |
| `AGENT__SESSION_INDEX_TTL_SECONDS` / `MAX` | `2592000` / `100` | 已废弃（2026-10-29），仅保留键名兼容 |
| `HITL__ENABLED` / `HITL__INTERRUPT_TTL_SECONDS` | `false` / `1800` | 人在回路 |
| `OPENUI__ENABLED` / `PROMPT_NAME` / `MAX_BLOCKS` | `false` / `openui` / `4` | 生成式 UI |
| `MCP__ENABLED` / `GATEWAY_URL` / `ALLOWED_TOOLS` | `false` / 空 / `[]` | 仅网关拓扑 |
| `RAG__RETRIEVER_MODULE` / `RAG__TOP_K` | 空 / `5` | 检索器已实现；部署模板默认开启并指向 `app.rag.knowledge.retriever` |
| `RAG__EMBEDDING_MODEL` / `DIMENSIONS` / `BATCH_SIZE` | 空 / `0` / `10` | 部署模板默认 `qwen:text-embedding-v4` / `1024` / `10`；启用内置检索器时模型与维度必填 |
| `RAG__MIN_RELEVANCE_SCORE` | `0.2` | 引用最小相关性阈值：向量余弦相似度低于该值的片段不展示；精确型号命中不受限制；`0` 关闭过滤 |
| `QWEN_API_KEY` | 空 | 根 `.env` 写入；Compose 映射为 LiteLLM 容器内 `DASHSCOPE_API_KEY`，供 embedding 条目使用 |
| `GUARD__ENABLED` / `MAX_INPUT_CHARS` / `BLOCK_ON_INJECTION` | `true` / `4000` / `true` | 输入护栏 |
| `RATE_LIMIT__ENABLED` / `CHAT_PER_MINUTE` / `WINDOW_SECONDS` / `FAIL_OPEN` | `true` / `20` / `60` / `true` | 对话限流 |
| `EVALS__USER_TOKEN` / `EVALS__USER_ID` | 空 | `--real` 评测 |
| `EVALS__PRICE_INPUT_PER_MILLION` / `EVALS__PRICE_OUTPUT_PER_MILLION` / `EVALS__PRICE_CURRENCY` | 空 / 空 / `CNY` | 评测报告折算成本；未配置时显示「未定价」 |
| `EVALS__E2E__AGENT_BASE_URL` / `EVALS__E2E__JAVA_BASE_URL` | `http://127.0.0.1:8000` / `http://127.0.0.1:8080` | `python -m evals.e2e --mode service` 的目标地址 |
| `EVALS__E2E__USERNAME` / `EVALS__E2E__PASSWORD` | `admin` / 空 | E2E 登录身份；口令只放本地 `.env`，未配置时退出码 2 |
| `EVALS__E2E__TIMEOUT_SECONDS` | `120` | 单轮 SSE 读取超时（1–600 秒） |
| `METRICS__ENABLED` | `true` | Prometheus 指标 |

### 2.7 前端与管理端

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `VITE_APP_TITLE` | `PC Build Agent` | 浏览器标题 |
| `VITE_API_BASE_URL` / `VITE_AGENT_BASE_URL` | `/api/v1` / `/agent/api/v1` | 同源代理前缀 |
| `VITE_OPENUI_ENABLED` | `false` | 与 Agent `OPENUI_ENABLED` 同步 |
| `VITE_SHOW_EXECUTION_TRACE` | `false` | 仅开发排查显示工具轨迹 |
| `ADMIN_APP_TITLE` | `Agent 管理后台` | 管理端标题；路径固定 `/admin/` |

### 2.8 数据治理脚本

| 变量 | 说明 |
| --- | --- |
| `DEEPSEEK_API_KEY` | 仅清洗脚本使用，禁止进入前端产物 |
| `JD_UNION_APP_KEY` / `JD_UNION_APP_SECRET` / `JD_UNION_SITE_ID` / `JD_UNION_ACCESS_TOKEN` | 京东联盟凭证；未配置时只做探测 |

## 3. 默认开关与部署基线（2026-11-17）

「代码默认」指未注入任何变量时的值；「`.env.example`」是部署模板值，已与当前本地启用状态对齐；「本机」是当前根 `.env` 与派生文件的实际值；「容器」表示 Compose 是否把根 `.env` 透传给 Agent。

> 代码回退值仍保持关闭：RAG/HITL 在 `STORAGE__BACKEND=memory`（Solo、单测）下开启会直接拒绝启动，因此只在部署模板与 Compose 中默认开启。

| 配置项 | 代码默认 | `.env.example` | 本机当前 | 容器透传 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `OPENUI_ENABLED` + `VITE_OPENUI_ENABLED` | `false` | `true` | `true` | 是 | 两端必须同值，否则一端不产出/一端不渲染 |
| `RAG_ENABLED` | `false` | `true` | `true` | 是 | 开启后必须给检索器模块与 embedding 模型/维度 |
| `RAG_EMBEDDING_MODEL` / `DIMENSIONS` | 空 / `0` | `qwen:text-embedding-v4` / `1024` | `qwen:text-embedding-v4` / `1024` | 是（已补齐） | 修前根 `.env` 缺这两项，容器内开 RAG 会启动失败 |
| `RAG_MIN_RELEVANCE_SCORE` | `0.2` | `0.2` | `0.2` | 是（已补齐） | 低于阈值的向量片段不展示 |
| `HITL_ENABLED` | `false` | `true` | `true` | 是 | 必须配 `STORAGE__BACKEND=postgres` |
| `MCP_ENABLED` | `false` | `false` | `false` | 是 | 仅网关拓扑；Solo 不支持 |
| `MULTI_AGENT_ENABLED` | `true` | `true` | `true` | 是（已补齐） | 关闭后退回单 Agent |
| `CRITIC_ENABLED` | `true` | `true` | `true` | 是（已补齐） | 仅多 Agent 开启时生效 |
| `SUMMARY_ENABLED` / `TRIGGER_TOKENS` | `false` / `5000` | `false` / `5000` | `false` / `5000` | 是（已补齐） | 开启会增加额外模型调用 |
| `MODEL_RUNTIME_ENABLED`（Java/Agent） | `false` | `true` | `true` | 是 | 控制面与 Agent 必须同值 |
| `BYOK_ENABLED`（Java） | `false` | `true` | `true` | 是 | 开启时 `MODEL_CRED_MASTER_KEY` 必须合法 |
| `MODEL_MANAGED_ENABLED`（Java） | `true` | `false` | `false` | 是 | 纯 BYOK 部署设为 `false` |
| `GUARD_ENABLED` / `RATE_LIMIT_ENABLED` | `true` | `true` | 未显式设置（用默认） | 是 | 默认开启，无需写进 `.env` |
| `VITE_SHOW_EXECUTION_TRACE` | `false` | `false` | `true` | 是 | **唯一建议保留差异**：生产建议 `false`，仅排查时临时开 |

Solo 模式在 [`.env.solo.example`](../../.env.solo.example) 中显式关闭 `RAG_ENABLED`，避免 memory 后端误开检索器。

**服务器与本地完全一致的最小设置**（其余值按生产替换密钥、域名与口令）：

```dotenv
SPRING_PROFILES_ACTIVE=prod
APP_ENV=prod
AUTH_COOKIE_SECURE=true
OPENUI_ENABLED=true
VITE_OPENUI_ENABLED=true
RAG_ENABLED=true
RAG_RETRIEVER_MODULE=app.rag.knowledge.retriever
RAG_EMBEDDING_MODEL=qwen:text-embedding-v4
RAG_EMBEDDING_DIMENSIONS=1024
RAG_MIN_RELEVANCE_SCORE=0.2
HITL_ENABLED=true
MODEL_RUNTIME_ENABLED=true
BYOK_ENABLED=true
MODEL_MANAGED_ENABLED=false
MULTI_AGENT_ENABLED=true
CRITIC_ENABLED=true
SUMMARY_ENABLED=false
```

- `DEBUG` 由 Compose 固定为 `false`，不要再从 `.env` 覆盖。
- `VITE_*` 会打进静态产物：改这些值必须重建 `frontend` / `admin` 镜像；其余变量重启对应容器即可。
- 本机 Agent 实际读取的是 `agent-service/.env`，该文件的托管块由 `scripts/config/generate-config.ps1` 从根 `.env` 派生，不要手改。

## 4. 生产 fail-fast

| 条件 | 行为 |
| --- | --- |
| `SPRING_PROFILES_ACTIVE=prod` 但 JWT/DB/内部凭据缺失或仍为占位 | Java 拒绝启动 |
| `prod` 下 `AUTH_COOKIE_SECURE=false` | Java 拒绝启动 |
| `prod` 下 `DEBUG=true` | Java / Agent 拒绝启动 |
| `BYOK_ENABLED=true` 但未启用模型运行时或主密钥非法 | Java 拒绝启动 |
| `prod` 下 `CORS_ORIGINS` 含 `*`，或 Agent `STORAGE__BACKEND!=postgres` | 对应服务拒绝启动 |
| `HITL__ENABLED=true` 且 `STORAGE__BACKEND=memory` | Agent 拒绝启动 |
| `RAG_ENABLED=true` 且检索器模块为空 | Agent 拒绝启动 |
| `RAG_ENABLED=true` 且内置检索器缺 embedding 模型或维度非正 | Agent 拒绝启动 |
| `prod` 下 `MODEL_RUNTIME__ENABLED=true` 但 `CONTROL_PLANE__CLIENT_SECRET` 为空或占位 | Agent 拒绝启动 |

补充：`AUTH_ADMIN_PASSWORD` 为空表示「不创建引导账号」，不会拒绝启动；首次上线必须确保已存在管理员账号。`AUTH__DEV_KID` 非空也不会拒绝启动，`/auth/dev-token` 在非 `dev` 或 `DEBUG=false` 时直接不可用。

## 5. 密钥生成与轮换

```powershell
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out jwt-private.pem
openssl rsa -in jwt-private.pem -pubout -out jwt-public.pem
openssl rand -base64 32   # BYOK 主密钥
```

- JWT 轮换：新增 `kid` 与公钥 → 两端同时配置 → 再切私钥；旧 `kid` 保留一个令牌周期。
- BYOK 主密钥轮换：递增 `MODEL_CRED_KEY_VERSION`，旧密钥放 `MODEL_CRED_MASTER_KEYS`；丢失主密钥等于凭证全部不可用。
- LiteLLM `LITELLM_SALT_KEY` 设置后不可更改。

## 6. 相关文档

- 部署与排障：[deployment-guide.md](./deployment-guide.md)
- 速查：[env-quick-reference.md](./env-quick-reference.md)
- Solo：[solo-mode.md](./solo-mode.md)
