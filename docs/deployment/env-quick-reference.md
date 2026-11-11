# 环境变量速查

| 项 | 内容 |
| --- | --- |
| 源文件 | `docs/deployment/environment-variables.md` |
| 性质 | 派生速查（权威以源文件为准，冲突时以源文件为准） |
| 核对日期 | 2026-11-03 |

## 基础设施（Compose / 数据库 / Redis）
| 变量名 | 必填性 | 默认值 | 用途 |
| --- | --- | --- | --- |
| `COMPOSE_PROJECT_NAME` | 否 | `pc-config-advisor` | 容器名前缀（同机多项目必须唯一） |
| `IMAGE_PREFIX` | 否 | `pc-config-advisor`（Compose 回退 `agent`） | 本地镜像 tag 前缀，避免多项目互相覆盖 |
| `WEB_PORT` | 否 | `80` | 前端宿主机端口，唯一公网入口 |
| `BACKEND_PORT` / `AGENT_PORT` | 否 | `8080` / `8000` | Java 与 Agent 宿主机端口，只绑 `127.0.0.1` |
| `SPRING_PROFILES_ACTIVE` / `APP_ENV` | 否 | `prod` / Compose `prod`，Agent `.env.example` 为 `dev` | Java 生效 profile 与 Agent 运行环境（`dev`/`staging`/`prod`） |
| `DEBUG` / `TZ` | 否 | `false` / `Asia/Shanghai` | Java 调试开关（Compose 固定 false）/ 容器时区 |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | 是 | `agent` / `replace-with-strong-db-password` / `agent` | 业务库账号、口令、库名（Java 专用） |
| `AGENT_POSTGRES_USER` / `AGENT_POSTGRES_PASSWORD` / `AGENT_POSTGRES_DB` | 是 | `agent` / `replace-with-strong-agent-db-password` / `agent_service` | Agent 会话库（pgvector）账号、口令、库名 |
| `DB_URL` | 是（prod 无默认） | Compose `jdbc:postgresql://postgres:5432/<POSTGRES_DB>`；local `jdbc:postgresql://localhost:5432/agent` | Java 数据源 URL |
| `DB_USERNAME` / `DB_PASSWORD` | 是 | Compose 取 `POSTGRES_USER` / `POSTGRES_PASSWORD`；local 账号 `agent`、口令无默认 | Java 数据源账号与口令 |
| `DB_POOL_MAX_SIZE` / `DB_POOL_MIN_IDLE` | 否 | `10` / `2`（prod `20` / `5`） | Hikari 最大连接数与最小空闲连接 |
| `REDIS_PASSWORD` | 是 | `replace-with-strong-redis-password` | Redis 口令，会拼进 `redis://` 连接串 |
| `REDIS__URL` / `REDIS__REQUIRED` | `REDIS__REQUIRED=true` 时必填 | Compose `redis://:<REDIS_PASSWORD>@redis:6379/0` / `true`（`.env.example` 为 `false`） | Agent Redis 连接串与硬依赖开关 |
| `REDIS__MAX_CONNECTIONS` / `REDIS__SOCKET_TIMEOUT_SECONDS` / `REDIS__CONNECT_TIMEOUT_SECONDS` / `REDIS__HEALTH_CHECK_INTERVAL_SECONDS` | 否 | `10` / `2` / `2` / `30` | 连接池、超时与探活（`0` 关闭探活） |
| `REDIS__KEY_PREFIX` | 否 | `agent`（1–32 字符，禁含冒号） | key 统一前缀，实际格式 `<KEY_PREFIX>:<APP_ENV>:<domain>:<parts...>` |
| `REDIS__DEFAULT_TTL_SECONDS` / `REDIS__LOCK_TTL_SECONDS` / `REDIS__IDEMPOTENCY_TTL_SECONDS` | 否 | `300` / `30` / `86400` | 缓存、分布式锁与幂等记录 TTL |
| 数据库宿主机端口覆盖变量名 | 源文件未定义 | 源文件未定义 | EV-03：未收录进任何 `.env.example`，改端口需直接改 `docker-compose.yml` |
## Java（application-service）
| 变量名 | 必填性 | 默认值 | 用途 |
| --- | --- | --- | --- |
| `JWT_PRIVATE_KEY` | 是 | 无 | RS256 签发私钥（PKCS#8 PEM），只注入 Java |
| `JWT_PUBLIC_KEY` | 是 | 无 | 对应公钥（X.509 PEM），Java 与 Agent 共用 |
| `JWT_KID` / `AUTH__JWT_KID` | 否 | `rsa-2026-10` | JWS 密钥标识，两端必须一致 |
| `JWT_ISSUER` / `AUTH__ISSUER` | 否 | `agent-application-service` | 签发方，两端必须一致 |
| `JWT_AUDIENCE` / `AUTH__AUDIENCE` | 否 | `agent-clients` | 受众，两端必须一致 |
| `JWT_ACCESS_TTL` | 否 | `10m` | Access Token 有效期 |
| `AUTH__JWT_PUBLIC_KEY` | 是 | 无 | Agent 侧验签公钥 |
| `AUTH__JWT_ALGORITHM` | 否 | `RS256` | 验签算法，写其他值启动即失败 |
| `AUTH__ACCESS_TOKEN_EXPIRE_MINUTES` / `AUTH__DEV_KID` / `AUTH__DEV_PRIVATE_KEY` | 否 | `60` / `rsa-dev` / 无 | 仅 `/auth/dev-token` 自签开发令牌；生产禁止注入私钥 |
| `AUTH_REFRESH_IDLE_TTL` | 否 | `7d` | 刷新令牌闲置失效期限 |
| `AUTH_REFRESH_ABSOLUTE_TTL` | 否 | `30d` | 自登录起绝对上限，刷新不延长 |
| `AUTH_REFRESH_ROTATION_GRACE` | 否 | `60s` | 并发刷新宽限期，窗口内旧令牌只返回 401 |
| `AUTH_COOKIE_SECURE` | 否 | `true`（YAML 兜底 `false`） | 刷新 Cookie 的 Secure 属性，生产必须为 true |
| `AUTH_ADMIN_USERNAME` / `AUTH_ADMIN_PASSWORD` / `AUTH_ADMIN_ROLES` | 口令 Compose 必填 | `admin` / `replace-with-strong-admin-password` / `ADMIN` | 播种管理账号；口令留空则不创建 |
| `AUTH_DEMO_USERNAME` / `AUTH_DEMO_PASSWORD` / `AUTH_DEMO_ROLES` | 否 | `demo` / 空 / `USER` | 播种演示账号；口令留空则不创建 |
| `CORS_ALLOWED_ORIGINS` | 否 | local `http://localhost:5173`，其余为空 | Java 跨域白名单（逗号分隔），也是 refresh/logout 来源校验依据 |
| `CORS_ORIGINS` | 否 | `["http://localhost:5173"]`；Compose 固定 `'["http://localhost"]'` | Agent 跨域白名单，必须是 JSON 数组 |
| `MODEL_RUNTIME_ENABLED` | 否 | `false` | 控制面总开关；关闭时 `/internal/v1/**` 与 `/api/v1/models` 返回 404 |
| `BYOK_ENABLED` | 否 | `false` | 用户自带密钥开关 |
| `MODEL_CRED_MASTER_KEY` | `BYOK_ENABLED=true` 时必填 | 空 | BYOK 凭证加密主密钥（32 字节 base64），只注入 Java |
| `MODEL_CRED_KEY_VERSION` / `MODEL_CRED_VERIFY_TIMEOUT` | 否 | `1` / `5s` | 新密文密钥版本与凭证远程验证超时 |
| `MODEL_CRED_MASTER_KEYS` | 否 | 空 | 多版本密钥环 `<version>:<base64>`，未配置回退单密钥 |
| `MODEL_DEFAULT_KEY` | 否 | `deepseek:deepseek-v4-pro` | Auto 对应的平台默认模型，格式 `<provider>:<modelKey>`；Provider 默认地址与探测模型由 LiteLLM 配置维护 |
| `MODEL_TASK_TTL` / `MODEL_TASK_CLEANUP_ENABLED` / `MODEL_TASK_CLEANUP_CRON` | 否 | `10m` / `true` / `"0 0 * * * *"` | 任务有效期（即幂等窗口）与过期任务清理 |
| `MODEL_QUOTA_DAILY_REQUESTS` / `MODEL_RECONCILE_ENABLED` / `MODEL_RECONCILE_CRON` | 否 | `100` / `true` / `"0 5 0 * * *"` | 每用户每日请求额度与对账定时任务 |
| `INTERNAL_AUTH_CLIENT_ID` / `INTERNAL_AUTH_CLIENT_SECRET` / `INTERNAL_AUTH_TOKEN_TTL` | 开启运行时后口令必填 | `agent-service` / `replace-with-strong-internal-client-secret` / `5m` | 服务令牌客户端凭据与有效期 |
## Agent（agent-service）
| 变量名 | 必填性 | 默认值 | 用途 |
| --- | --- | --- | --- |
| `MODEL_RUNTIME__ENABLED` | 否 | `false` | Agent 运行期解析开关；关闭时不发起控制面出站请求 |
| `CONTROL_PLANE__BASE_URL` | 否 | 容器 `http://application-service:8080`；`.env.example` 为 `http://127.0.0.1:8080` | Java 内部地址，必须是 http/https |
| `CONTROL_PLANE__CLIENT_ID` | 否 | `agent-service` | 服务客户端标识，需等于 `INTERNAL_AUTH_CLIENT_ID` |
| `CONTROL_PLANE__CLIENT_SECRET` | 开启运行时后必填 | 无 | 服务令牌口令，需等于 `INTERNAL_AUTH_CLIENT_SECRET` |
| `CONTROL_PLANE__TIMEOUT_SECONDS` | 否 | `5`（0 < t ≤ 60） | 控制面调用超时 |
| `LLM__GATEWAY_API_KEY` / `LLM__GATEWAY_BASE_URL` | 网关模式必填 / 否 | 与 `LITELLM_MASTER_KEY` 一致 / `http://litellm:4000` | 模型统一出口；未配置密钥时退化为直连模式（Solo） |
| `LLM_API_KEY` / `LLM__API_KEY` | Solo 必填 / Solo 必填 | 无 | 直连模式平台密钥 |
| `LLM_MODEL` / `LLM__MODEL` | 否 | `deepseek:deepseek-v4-pro` | 网关 `model_list` 中的 `model_name` |
| `LLM_BASE_URL` / `LLM__BASE_URL` | 否 | `https://api.deepseek.com/v1` | 仅直连模式（Solo）使用 |
| `LITELLM_MASTER_KEY` / `LITELLM_SALT_KEY` | Compose 必填 | 无 | 网关管理口令与加密盐，口令同时注入 Agent 与 Java |
| `MODEL_GATEWAY_BASE_URL` / `MODEL_GATEWAY_MASTER_KEY` | 否 / 探测必填 | `http://litellm:4000` / 同 master key | Java 侧 BYOK 凭证探测 |
| `LLM_MAX_TOKENS` / `LLM__MAX_TOKENS` | 否 | `2048` | 单次生成 token 上限 |
| `LLM__TEMPERATURE` / `LLM__TIMEOUT_SECONDS` | 否 | `0.7`（0–2）/ `60` | 采样温度与单次调用超时 |
| `APP_NAME` / `API_PREFIX` | 否 | `agent-service` / `/api/v1` | 服务标识与所有路由前缀 |
| `STORAGE__BACKEND` | 否 | Compose `postgres`；代码默认 `memory` | 会话持久化后端，prod 必须 postgres |
| `STORAGE__POSTGRES_URL` | `backend=postgres` 时必填 | Compose 由 `AGENT_POSTGRES_*` 拼出 | 会话库连接串 |
| `STORAGE__POOL_SIZE` / `STORAGE__AUTO_SETUP` | 否 | `5`（1–50）/ `true` | 连接池上限与启动时幂等建表 |
| `AGENT__CONTEXT_MAX_TOKENS` / `AGENT__RECURSION_LIMIT` | 否 | `6000` / `12`（1–100） | 上下文预算与 ReAct 循环上限 |
| `AGENT__REQUEST_TIMEOUT_SECONDS` / `AGENT__SSE_HEARTBEAT_SECONDS` | 否 | `120` / `15` | 单次流总超时与 SSE 心跳注释间隔 |
| `AGENT__THREAD_LOCK_TTL_SECONDS` / `AGENT__THREAD_LOCK_WAIT_SECONDS` | 否 | `300` / `3`（`0` 表示立即 409） | 同会话串行化锁持有与抢锁等待 |
| `AGENT__SYSTEM_PROMPT` | 否 | `default` | 提示词文件名（不含 `.md`），启动校验文件存在 |
| `AGENT__TOOL_TIMEOUT_SECONDS` / `AGENT__TOOL_MAX_RETRIES` | 否 | `10` / `1`（0–5） | 工具默认超时与失败重试次数 |
| `AGENT__TOOL_MAX_OUTPUT_TOKENS` | 否 | `2000` | 工具单次返回的 token 上限，超出截断并附加提示 |
| `AGENT__TOOL_MAX_CALLS_PER_TURN` | 否 | `3`（1–20） | 同一工具单轮调用上限，超限返回提示文本而不抛错 |
| `AGENT__TOOL_REDACT_OUTPUT` | 否 | `true` | 工具返回给模型前脱敏（手机号、邮箱、身份证、API Key / Bearer） |
| `AGENT__TOOL_MODULES` | 否 | 空 | 追加的工具模块（点分路径，逗号分隔）；内置与 `tools_ext` 无需声明 |
| `AGENT__HOOKS_MODULES` | 否 | 空 | 生命周期钩子模块（点分路径，逗号分隔）；导入失败拒绝启动 |
| `AGENT__SUMMARY_ENABLED` / `AGENT__SUMMARY_TRIGGER_TOKENS` | 否 | `false` / `5000` | 长会话摘要开关与触发阈值；摘要只影响本次模型输入、不落库 |
| `AGENT__PROFILES_DIR` | 否 | `app/agents` | Agent Profile 配置目录；相对路径按服务根目录解析，子目录 YAML 也会加载 |
| `AGENT__DEFAULT_PROFILE` | 否 | `default` | 请求未携带 `agent_id` 时使用的 Profile，启动校验必须存在 |
| `AGENT__SESSION_INDEX_TTL_SECONDS` / `AGENT__SESSION_INDEX_MAX` | 否 | `2592000` / `100` | 已废弃（2026-10-29），仅为兼容旧 `.env` 保留 |
| `OPENUI__ENABLED` / `OPENUI__PROMPT_NAME` | 否 | `false` / `openui` | 生成式 UI 总开关与组件契约文件名 |
| `OPENUI__MAX_BLOCKS` | 否 | `4`（1–10） | 单次回答顶层 UI 块上限，仅写入提示词 |
| `HITL__ENABLED` | 否 | `false` | 人在回路总开关；开启时 `STORAGE__BACKEND` 必须为 `postgres`，否则启动失败 |
| `HITL__INTERRUPT_TTL_SECONDS` | 否 | `1800`（1–86400） | 中断有效期；超时恢复返回 `interrupt_expired` |
| `MCP__ENABLED` / `MCP__GATEWAY_URL` | 否 | `false` / 空 | MCP 总开关与聚合端点覆盖值；留空由 `LLM__GATEWAY_BASE_URL + /mcp` 推导，Solo 无网关故不生效 |
| `MCP__ALLOWED_TOOLS` | 否 | `[]` | 只接入列出的工具（网关返回的原始工具名，JSON 数组）；为空表示全部 |
| `MCP__CONNECT_TIMEOUT_SECONDS` / `MCP__REQUEST_TIMEOUT_SECONDS` | 否 | `10` / `30` | 建连总超时与单次 MCP 工具调用超时；后者必须大于网关侧 `timeout` |
| `RAG__ENABLED` / `RAG__RETRIEVER_MODULE` | `ENABLED=true` 时 `MODULE` 必填 | `false` / 空 | 可选 RAG 开关与检索器模块（点分路径，需暴露 `create_retriever()`）；关闭时不导入、不发请求 |
| `RAG__TOP_K` | 否 | `5`（1–20） | 单轮检索返回的引用条数上限 |
| `METRICS__ENABLED` / `METRICS__TOKEN` | 否 | `true` / 空 | 指标端点开关与应用内兜底令牌（16–128 字符） |
| `LANGSMITH_TRACING` / `LANGSMITH_API_KEY` / `LANGSMITH_PROJECT` / `LANGSMITH_ENDPOINT` | 否 | 未设置 | LangSmith 追踪开关、凭据与目标 |
## 前端与管理端（构建期写死进静态产物）
| 变量名 | 必填性 | 默认值 | 用途 |
| --- | --- | --- | --- |
| `VITE_APP_TITLE` / `VITE_API_BASE_URL` | 是 | `Agent Analytics`（Compose），`frontend/.env.example` 为 `Agent` / `/api/v1` | 用户端标题与 Java 接口基址 |
| `VITE_APP_ENV` / `VITE_AGENT_BASE_URL` / `VITE_API_TIMEOUT` / `VITE_USE_MOCK` / `VITE_OPENUI_ENABLED` | `VITE_APP_ENV` 是，其余否 | `production` / `/agent/api/v1` / `10000` / `false` / `false` | 构建环境、Agent 基址、超时、Mock 与生成式 UI 开关（须与 `OPENUI__ENABLED` 同步） |
| `ADMIN_APP_TITLE` / `VITE_BASE_PATH` | 否 | `Agent 管理后台` / `/admin/` | 管理端标题（映射为 `VITE_APP_TITLE` build arg）与部署前缀 |
完整说明见源文件：docs/deployment/environment-variables.md
