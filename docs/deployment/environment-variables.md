# 环境变量权威表

| 属性 | 内容 |
| --- | --- |
| 状态 | Current |
| 最后核验 | 2026-11-04 |
| 权威性 | Authoritative（环境变量名、默认值、必填性、生产 fail-fast 的唯一维护点） |
| 适用范围 | 根 `.env`、各端运行时环境变量与构建参数 |
| 主要证据 | `根 .env.example`、`deploy/.env.example`、`application-service/.env.example`、`agent-service/.env.example`、`frontend/.env.example`、`docker-compose.yml`、`deploy/docker-compose.infra.yml`、`application-service/src/main/resources/application{,-local,-prod}.yaml`、`agent-service/app/core/config.py`、`application-service/src/main/java/com/example/agent/shared/config/ProdConfigGuard.java`、`application-service/src/main/java/com/example/agent/shared/config/ModelRuntimeProperties.java` |

**维护规则**：同一事实只在本文件维护。其他文档（含 `docs/deployment/deployment-guide.md`、服务文档、README）只链接本文件，**不复制变量表**；变量名、默认值、必填性只以 `*.env.example` 与可执行配置为准，本文件是它们的说明。

冲突优先级：**代码/Compose/YAML > `*.env.example` > 本文件 > 历史归档**。发现不一致时先修 `.env.example` 与代码，再改本文件。

---

## 1. 读取链路

```text
根 .env ──docker compose──▶ 容器环境变量 ──▶ 服务启动期绑定
                                            ├─ Java：application*.yaml 的 ${...} 占位符
                                            ├─ Agent：Pydantic Settings（__ 嵌套）
                                            └─ 前端：VITE_* 在镜像构建期写死进静态产物
```

- 根 `.env` 由 `.gitignore` 忽略，仅存在于部署机；仓库只提交 `.env.example`。
- Compose 用 `${VAR:?message}` 表达「缺失即报错」，因此容器里的变量有两类：**Compose 直接透传**与**Compose 重组**（如 `STORAGE__POSTGRES_URL` 由三段数据库变量拼出）。
- 只改运行时环境变量（数据库、JWT、LLM、Redis）**不需要重建镜像**，重启容器即可；改 `VITE_*`、源码或 Dockerfile **必须重建**对应镜像（见 `docs/deployment/deployment-guide.md` §6）。

---

## 2. 变量总表

列说明：「必填」指 Compose 启动/服务启动是否必需；「生产 fail-fast」指真有一处启动期校验会拒绝非法值，无校验的项会标注为「无」。

### 2.1 Compose 编排

| 变量 | 作用 | 默认值 / 示例 | 必填 | 生产 fail-fast | 证据 |
| --- | --- | --- | --- | --- | --- |
| `COMPOSE_PROJECT_NAME` | 容器名 / 卷名 / 网络名前缀 | `pc-config-advisor` | 否 | 无 | `根 .env.example`；`docker-compose.yml` L23 |
| `IMAGE_PREFIX` | 本地构建镜像的仓库前缀 | `pc-config-advisor`（Compose 回退 `agent`） | 否 | 无 | `docker-compose.yml` 各服务 `image` |
| `WEB_PORT` | 前端宿主机端口（唯一对外入口） | `80` | 否 | 无 | `docker-compose.yml` L267 |
| `BACKEND_PORT` | Java 宿主机端口，只绑 `127.0.0.1` | `8080` | 否 | 无 | `docker-compose.yml` L154 |
| `AGENT_PORT` | Agent 宿主机端口，只绑 `127.0.0.1` | `8000` | 否 | 无 | `docker-compose.yml` L222 |
| `PROMETHEUS_PORT` | 指标采集器宿主机端口，只绑 `127.0.0.1` | `9090` | 否 | 无 | `docker-compose.yml` `prometheus.ports`；`根 .env.example` |
| `SPRING_PROFILES_ACTIVE` | Java 生效 profile | Compose 默认 `prod` | 否 | **间接**：`prod` 会激活 `ProdConfigGuard` | `docker-compose.yml` L109 |
| `APP_ENV` | Agent 运行环境，只接受 `dev` / `staging` / `prod` | Compose 默认 `prod`；`agent-service/.env.example` 为 `dev` | 否 | **是**：`prod` 触发 Agent 生产校验 | `docker-compose.yml` L182；`config.py` L319 |
| `DEBUG` | Java 调试开关；Compose 固定写死 `"false"` | `false` | 否 | **是**：`prod` 下 `true` 拒绝启动 | `docker-compose.yml` L111；`ProdConfigGuard.java` L69-71 |
| `TZ` | 容器时区 | `Asia/Shanghai` | 否 | 无 | `docker-compose.yml` 各服务 `environment` |

> 数据库/Redis 的宿主机端口默认分别为 `5432`、`5433`、`6379`（见 §2.2、§2.3 的 `ports` 证据）。Compose 允许用同名覆盖变量改写这些端口，但这些变量当前**未收录**进任何 `.env.example`，因此本表不列其全名；需要改端口时直接看 `docker-compose.yml` 的 `ports` 段，并同步在根 `.env.example` 登记。

### 2.2 数据库（业务库 / Agent 库）

| 变量 | 作用 | 默认值 / 示例 | 必填 | 生产 fail-fast | 证据 |
| --- | --- | --- | --- | --- | --- |
| `POSTGRES_USER` | 业务库账号（Java 专用） | `agent` | **是**（`${POSTGRES_USER:?...}`） | 无 | `根 .env.example`；`docker-compose.yml` L26 |
| `POSTGRES_PASSWORD` | 业务库口令 | `replace-with-strong-db-password` | **是** | **是**：`spring.datasource.password` 为空或占位符时拒绝启动 | `docker-compose.yml` L27；`ProdConfigGuard.java` L176-189 |
| `POSTGRES_DB` | 业务库名 | `agent` | **是** | 无 | `docker-compose.yml` L28 |
| `AGENT_POSTGRES_USER` | Agent 会话库账号（pgvector） | `agent` | **是** | 无 | `docker-compose.yml` L53 |
| `AGENT_POSTGRES_PASSWORD` | Agent 会话库口令 | `replace-with-strong-agent-db-password` | **是** | 无（Agent 侧只有连接失败） | 同上 L54 |
| `AGENT_POSTGRES_DB` | Agent 会话库名 | `agent_service` | **是** | 无 | 同上 L55 |
| `DB_URL` | Java 数据源 URL | Compose：`jdbc:postgresql://postgres:5432/<POSTGRES_DB>`；`local` profile：`jdbc:postgresql://localhost:5432/agent` | **是**（`prod` 无默认） | **是**：为空或未解析占位符拒绝启动 | `docker-compose.yml` L112；`application-prod.yaml` L3；`application-local.yaml` L3 |
| `DB_USERNAME` | Java 数据源账号 | Compose 取自 `POSTGRES_USER`；`local` 默认 `agent` | **是** | 无 | `docker-compose.yml` L113；`application-local.yaml` L5 |
| `DB_PASSWORD` | Java 数据源口令 | Compose 取自 `POSTGRES_PASSWORD`；`local` 无默认 | **是** | **是**（见 `POSTGRES_PASSWORD` 行） | `docker-compose.yml` L114；`application-local.yaml` L7 |
| `DB_POOL_MAX_SIZE` | Hikari 最大连接数 | `local` `10`、`prod` `20` | 否 | 无 | `application-local.yaml` L7；`application-prod.yaml` L7 |
| `DB_POOL_MIN_IDLE` | Hikari 最小空闲连接 | `local` `2`、`prod` `5` | 否 | 无 | 同上 |

> `application-service/.env.example` 只服务于该服务自带的本地 Compose（`POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`），与 Java 运行时变量不是同一套，不要混用。

### 2.3 Redis

| 变量 | 作用 | 默认值 / 示例 | 必填 | 生产 fail-fast | 证据 |
| --- | --- | --- | --- | --- | --- |
| `REDIS_PASSWORD` | Redis 口令；会拼进 `redis://` 连接串 | `replace-with-strong-redis-password` | **是** | 无 | `docker-compose.yml` L82、L201 |
| `REDIS__URL` | Agent Redis 连接串 | Compose：`redis://:<REDIS_PASSWORD>@redis:6379/0`；本地示例注释值 `redis://:password@127.0.0.1:6379/0` | `REDIS__REQUIRED=true` 时必填 | **是**：`prod` 下为空或 `REDIS__REQUIRED!=true` 拒绝启动 | `docker-compose.yml` L201；`agent-service/.env.example` L72；`config.py` L361-362 |
| `REDIS__REQUIRED` | Redis 是否硬依赖 | Compose `"true"`；`.env.example` `false` | 否 | **是**：`prod` 必须为 `true` | `docker-compose.yml` L202；`config.py` L361-362 |
| `REDIS__MAX_CONNECTIONS` | 连接池上限 | `10`（1–200） | 否 | 无 | `config.py` L200 |
| `REDIS__SOCKET_TIMEOUT_SECONDS` | Socket 超时 | `2`（>0） | 否 | 无 | `config.py` L201 |
| `REDIS__CONNECT_TIMEOUT_SECONDS` | 连接超时 | `2`（>0） | 否 | 无 | `config.py` L202 |
| `REDIS__HEALTH_CHECK_INTERVAL_SECONDS` | 空闲探活间隔，`0` 关闭 | `30` | 否 | 无 | `config.py` L204 |
| `REDIS__KEY_PREFIX` | key 统一前缀 | `agent`（1–32 字符，禁含冒号与首尾空格） | 否 | 字段级：含冒号即启动失败 | `config.py` L206、L222-228 |
| `REDIS__DEFAULT_TTL_SECONDS` | 缓存类 key 默认 TTL | `300` | 否 | 无 | `config.py` L208 |
| `REDIS__LOCK_TTL_SECONDS` | 分布式锁持有时间 | `30` | 否 | 无 | `config.py` L210 |
| `REDIS__IDEMPOTENCY_TTL_SECONDS` | 幂等记录保留时间 | `86400` | 否 | 无 | `config.py` L212 |

key 实际格式为 `<KEY_PREFIX>:<APP_ENV>:<domain>:<parts...>`（如 `agent:prod:cache:user:123`）。

### 2.4 JWT 与验签（Java 签发，Agent 只验签）

| 变量 | 作用 | 默认值 / 示例 | 必填 | 生产 fail-fast | 证据 |
| --- | --- | --- | --- | --- | --- |
| `JWT_PRIVATE_KEY` | RS256 签发私钥（PKCS#8 PEM），**只注入 Java** | 无 | **是** | **是**：空/占位/PEM 非法 → 拒绝启动 | `application.yaml` L58；`ProdConfigGuard.java` L99-122 |
| `JWT_PUBLIC_KEY` | 对应公钥（X.509 PEM），Java 与 Agent 共用 | 无 | **是** | **是**：空/占位/非法，或与私钥不成对 → 拒绝启动 | `application.yaml` L59；`ProdConfigGuard.java` L106-110 |
| `JWT_KID` | 写入 JWS Header 的密钥标识 | `rsa-2026-10` | 否 | 无（但两端不一致会导致 Agent 全部 401） | `application.yaml` L60 |
| `JWT_ISSUER` | 签发方 | `agent-application-service` | 否 | 无 | `application.yaml` L62 |
| `JWT_AUDIENCE` | 受众 | `agent-clients` | 否 | **是**：为空或占位符拒绝启动 | `application.yaml` L61；`ProdConfigGuard.java` L149-154 |
| `JWT_ACCESS_TTL` | Access Token 有效期 | `10m` | 否 | 无 | `application.yaml` L63 |
| `AUTH__JWT_PUBLIC_KEY` | Agent 侧验签公钥（= `JWT_PUBLIC_KEY`） | 无（必填） | **是** | **是**：为空、占位片段或 PEM 不可解析 → 拒绝启动 | `docker-compose.yml` L188；`config.py` L78-101、L348-351 |
| `AUTH__JWT_ALGORITHM` | 验签算法，类型收窄为字面量 `RS256` | `RS256` | 否 | 字段级：写其他值启动即失败（杜绝 HS* 混淆与 `alg=none`） | `config.py` L66 |
| `AUTH__JWT_KID` | Agent 侧密钥标识（= `JWT_KID`） | `rsa-2026-10` | 否 | 无（不一致即全部 401） | `docker-compose.yml` L190 |
| `AUTH__ISSUER` | Agent 校验的签发方（= `JWT_ISSUER`） | `agent-application-service` | 否 | 无 | `config.py` L68 |
| `AUTH__AUDIENCE` | Agent 强制校验的受众（= `JWT_AUDIENCE`） | `agent-clients` | 否 | 字段级：空字符串被拒绝（有默认值，不是必填） | `config.py` L70、L119-126 |
| `AUTH__ACCESS_TOKEN_EXPIRE_MINUTES` | **仅** Agent 自签开发令牌的有效期 | `60` | 否 | 无 | `config.py` L76 |
| `AUTH__DEV_KID` | 开发令牌 kid，与生产 kid 区分 | `rsa-dev` | 否 | 无 | `config.py` L75 |
| `AUTH__DEV_PRIVATE_KEY` | 仅 `/auth/dev-token` 自签使用；生产**禁止**注入 | 无（`.env.example` 中注释） | 否 | 无（接口本身受 `APP_ENV`/`DEBUG` 双重限制） | `config.py` L73-74、L103-109；`agent-service/.env.example` L54 |

历史变量名 `AUTH__JWT_ISSUER` / `AUTH__JWT_SECRET` 已于 2026-10-28/10-29 移除；误写会因 `extra="ignore"` **静默失效**（见 §6 A-02），不会报错。

### 2.5 Refresh Token 与 Cookie

| 变量 | 作用 | 默认值 / 示例 | 必填 | 生产 fail-fast | 证据 |
| --- | --- | --- | --- | --- | --- |
| `AUTH_REFRESH_IDLE_TTL` | 刷新令牌闲置失效期限 | `7d` | 否 | 无 | `application.yaml` L66 |
| `AUTH_REFRESH_ABSOLUTE_TTL` | 自登录起绝对上限，刷新不延长 | `30d` | 否 | 无 | `application.yaml` L67 |
| `AUTH_REFRESH_ROTATION_GRACE` | 并发刷新宽限期，窗口内旧令牌只返回 401、不撤销整族 | `60s` | 否 | 无 | `application.yaml` L69 |
| `AUTH_COOKIE_SECURE` | 刷新 Cookie 的 `Secure` 属性 | `true`（`根 .env.example`、Compose）；`application.yaml` 兜底默认 `false` | 否 | **是**：`prod` 下必须为 `true` | `application.yaml` L72；`docker-compose.yml` L128；`ProdConfigGuard.java` L162-167 |

### 2.6 临时引导账号

| 变量 | 作用 | 默认值 / 示例 | 必填 | 生产 fail-fast | 证据 |
| --- | --- | --- | --- | --- | --- |
| `AUTH_ADMIN_USERNAME` | 播种管理账号用户名 | `admin` | 否 | 无 | `application.yaml` L75 |
| `AUTH_ADMIN_PASSWORD` | 管理账号口令；**留空则不创建账号** | 无（`replace-with-strong-admin-password`） | Compose 启动必填（`${AUTH_ADMIN_PASSWORD:?...}`） | 无 | `docker-compose.yml` L130 |
| `AUTH_ADMIN_ROLES` | 管理账号角色（不要带 `ROLE_` 前缀） | `ADMIN` | 否 | 无 | `application.yaml` L77 |
| `AUTH_DEMO_USERNAME` | 演示账号用户名 | `demo` | 否 | 无 | `application.yaml` L78 |
| `AUTH_DEMO_PASSWORD` | 演示账号口令；留空即不创建 | 空 | 否 | 无 | `docker-compose.yml` L134 |
| `AUTH_DEMO_ROLES` | 演示账号角色 | `USER` | 否 | 无 | `application.yaml` L80 |

仅在首次启动且用户名不存在时播种；生产建议只保留 admin，demo 留空。

### 2.7 CORS

| 变量 | 作用 | 默认值 / 示例 | 必填 | 生产 fail-fast | 证据 |
| --- | --- | --- | --- | --- | --- |
| `CORS_ALLOWED_ORIGINS` | Java 跨域白名单，英文逗号分隔；同源部署留空 | `local` profile 默认 `http://localhost:5173`，其余为空 | 否 | 无（`.env.example` 与代码均禁止通配，但无启动期校验） | `application.yaml` L83；`application-local.yaml` L15 |
| `CORS_ORIGINS` | Agent 跨域白名单，**必须是合法 JSON 数组**，不能写逗号分隔 | `["http://localhost:5173"]`；Compose 固定 `'["http://localhost"]'` | 否 | **是**（仅 Agent）：`prod` 下含 `*` 拒绝启动 | `config.py` L323、L354-355；`docker-compose.yml` L186 |

`CORS_ALLOWED_ORIGINS` 同时是 `/auth/refresh`、`/auth/logout` 的来源校验依据（见 `docs/services/application-service/security.md`）。

### 2.8 模型运行时控制面（Java）

| 变量 | 作用 | 默认值 / 示例 | 必填 | 生产 fail-fast | 证据 |
| --- | --- | --- | --- | --- | --- |
| `MODEL_RUNTIME_ENABLED` | 控制面总开关；关闭时 `/internal/v1/**` 与 `/api/v1/models` 返回 404 | `false` | 否 | 无 | `application.yaml` L20 |
| `BYOK_ENABLED` | 用户自带密钥开关 | `false` | 否 | **是**（Bean Validation）：为 `true` 时必须同时开启运行时且主密钥可用 | `application.yaml` L21；`ModelRuntimeProperties.java` L92-98 |
| `MODEL_MANAGED_ENABLED` | 平台托管模型开关；`false` 时目录不返回平台模型，Auto 只落到用户 BYOK 模型 | `true` | 否 | 否 | `application.yaml` L23；`ModelRuntimeProperties.java` |
| `MODEL_MANAGED_PROBE_TTL` | 平台密钥可用性探测缓存时长；探测失败会立即隐藏平台模型 | `30s` | 否 | 否 | `application.yaml`；`ManagedModelAvailability.java` |
| `MODEL_CRED_MASTER_KEY` | BYOK 凭证加密主密钥（32 字节 base64） | 空 | `BYOK_ENABLED=true` 时必填 | **是**（同上 `@AssertTrue`） | `application.yaml` L24；`ModelRuntimeProperties.java` L92-98 |
| `MODEL_CRED_KEY_VERSION` | 新密文使用的密钥版本 | `1` | 否 | 无 | `application.yaml` L25 |
| `MODEL_CRED_MASTER_KEYS` | 多版本密钥环，格式 `<version>:<base64>`，英文逗号分隔 | 空 | 否 | 无；未配置时回退单密钥 `MODEL_CRED_MASTER_KEY` | `application.yaml` L27；`ModelRuntimeProperties.java` L220-232 |
| `MODEL_CRED_VERIFY_TIMEOUT` | 凭证远程验证超时 | `5s` | 否 | 无 | `application.yaml` L28 |
| `MODEL_CRED_VERIFY_RATE_LIMIT_PER_MINUTE` | 单用户每分钟手动验证次数上限，超限返回 429 `40222` | `5` | 否 | 无 | `application.yaml` 模型段；`ModelCredentialVerifyRateLimiter.java` |
| `MODEL_DEFAULT_KEY` | Auto 对应的平台默认模型，格式 `<provider>:<modelKey>` | `deepseek:deepseek-v4-pro` | 否 | 无 | `application.yaml` L34 |
| `MODEL_TASK_TTL` | 运行时任务有效期，同时是幂等窗口 | `10m` | 否 | 无 | `application.yaml` L35 |
| `MODEL_TASK_CLEANUP_ENABLED` | 过期任务清理开关（只置 EXPIRED，不物理删除） | `true` | 否 | 无 | `application.yaml` L46 |
| `MODEL_TASK_CLEANUP_CRON` | 清理 cron（UTC，6 段含秒） | `"0 0 * * * *"` | 否 | 无 | `application.yaml` L48 |
| `MODEL_QUOTA_DAILY_REQUESTS` | 每用户每日请求额度（产品配置，非 Provider 费用额度） | `100` | 否 | **是**（Bean Validation）：`@Min(1)` | `application.yaml` L38；`ModelRuntimeProperties.java` L105 |
| `MODEL_RECONCILE_ENABLED` | 对账定时任务开关（只读统计） | `true` | 否 | 无 | `application.yaml` L41 |
| `MODEL_RECONCILE_CRON` | 对账 cron（UTC），默认每日 00:05 | `"0 5 0 * * *"` | 否 | **是**（Bean Validation）：`@NotBlank` | `application.yaml` L43；`ModelRuntimeProperties.java` L123 |
| `INTERNAL_AUTH_CLIENT_ID` | Agent 换取服务令牌的 client id | `agent-service` | 否 | 无 | `application.yaml` L50 |
| `INTERNAL_AUTH_CLIENT_SECRET` | 服务令牌口令 | 无（`replace-with-strong-internal-client-secret`） | 开启运行时后必填 | **是**：开启运行时后为空/占位/短于 16 字符 → 拒绝启动 | `application.yaml` L52；`ProdConfigGuard.java` L32、L197-210；`ModelRuntimeProperties.java` L75-82 |
| `INTERNAL_AUTH_TOKEN_TTL` | 服务令牌有效期 | `5m` | 否 | 无 | `application.yaml` L53 |

cron 含空格，`.env` 与 YAML 中必须整体加引号。

### 2.9 模型运行时调用侧（Agent）

| 变量 | 作用 | 默认值 / 示例 | 必填 | 生产 fail-fast | 证据 |
| --- | --- | --- | --- | --- | --- |
| `MODEL_RUNTIME__ENABLED` | Agent 运行期解析总开关；关闭时不发起任何控制面出站请求 | `false` | 否 | **是**（仅 `prod`）：开启时必须配置真实 `CONTROL_PLANE__CLIENT_SECRET` | `docker-compose.yml` L213；`config.py` L363-374 |
| `CONTROL_PLANE__BASE_URL` | Java 内部地址 | 容器 `http://application-service:8080`；`agent-service/.env.example` 为 `http://127.0.0.1:8080` | 否 | 字段级：必须是 http/https，末尾斜杠会被去掉 | `docker-compose.yml` L217；`config.py` L151-158 |
| `CONTROL_PLANE__CLIENT_ID` | 服务客户端标识，必须等于 `INTERNAL_AUTH_CLIENT_ID` | `agent-service`（1–64 字符） | 否 | 无 | `docker-compose.yml` L219；`config.py` L147 |
| `CONTROL_PLANE__CLIENT_SECRET` | 服务令牌口令，必须等于 `INTERNAL_AUTH_CLIENT_SECRET` | 无 | 开启运行时后必填 | **是**（仅 `prod`，见上） | `docker-compose.yml` L220；`config.py` L363-374 |
| `CONTROL_PLANE__TIMEOUT_SECONDS` | 控制面调用超时 | `5`（0 < t ≤ 60） | 否 | 字段级上限 | `docker-compose.yml` L221；`config.py` L149 |

### 2.10 大模型

| 变量 | 作用 | 默认值 / 示例 | 必填 | 生产 fail-fast | 证据 |
| --- | --- | --- | --- | --- | --- |
| `LLM__GATEWAY_API_KEY` | 网关鉴权密钥（LiteLLM master key）；配置后进入网关模式 | 与 `LITELLM_MASTER_KEY` 一致 | 网关模式必填 | **是**：以 `sk-replace` 开头拒绝启动 | `docker-compose.yml` Agent 段；`config.py` |
| `LLM_GATEWAY_API_KEY` | 容器内覆盖 Agent 网关密钥；不填则继承 `LITELLM_MASTER_KEY` | 空（Solo）；完整模式通常不填 | 否 | 无 | `docker-compose.yml` Agent 段 |
| `LLM__GATEWAY_BASE_URL` | Agent 请求的网关地址 | 容器内 `http://litellm:4000`；宿主机 `http://127.0.0.1:4000` | 否 | 无 | 同上 |
| `LLM_API_KEY` | 直连模式（Solo）的平台密钥 | 无（`sk-replace-with-your-real-key`） | Solo 必填 | **是**（Agent，仅 `prod`） | `docker-compose.yml`；`config.py` |
| `LLM__API_KEY` | Agent 侧同义（`SecretStr`） | 无 | Solo 必填 | 同上 | `config.py` |
| `LLM_MODEL` / `LLM__MODEL` | 模型标识；网关模式下即 `model_list` 的 `model_name` | `deepseek:deepseek-v4-pro` | 否 | 无 | `docker-compose.yml`；`config.py` |
| `LLM_BASE_URL` / `LLM__BASE_URL` | 直连模式接入地址；网关模式不使用 | `https://api.deepseek.com/v1` | 否 | 无 | 同上 |
| `LLM_MAX_TOKENS` / `LLM__MAX_TOKENS` | 单次生成 token 上限 | `2048` | 否 | 无 | `docker-compose.yml`；`config.py` |
| `LLM__TEMPERATURE` | 采样温度（0–2） | `0.7` | 否 | 字段级范围校验 | `config.py` |
| `LLM__TIMEOUT_SECONDS` | 单次调用超时 | `60` | 否 | 字段级（>0） | `config.py` |

> Provider 协议、默认接入地址、跨 Provider 故障切换统一由 LiteLLM 承担（ADR 0008）。Agent 不再维护 Provider 白名单；`LLM_PROVIDER` / `LLM_PROVIDER_BASE_URLS` 已移除，出现也只是未使用的环境变量。

### 2.10.1 模型网关（LiteLLM）

| 变量 | 作用 | 默认值 / 示例 | 必填 | 生产 fail-fast | 证据 |
| --- | --- | --- | --- | --- | --- |
| `LITELLM_MASTER_KEY` | 网关管理口令；同时注入 Agent 与 Java 作为出站鉴权 | 无 | Compose 必填（`${LITELLM_MASTER_KEY:?...}`） | 启动期缺失即拒绝 | `docker-compose.yml` litellm 段 |
| `LITELLM_SALT_KEY` | 网关内部字段加密盐，设置后不可更改 | 无 | Compose 必填 | 启动期缺失即拒绝 | 同上 |
| `LITELLM_PORT` | 宿主机回环映射端口 | `4000` | 否 | 只绑定 `127.0.0.1` | 同上 |
| `MODEL_GATEWAY_BASE_URL` | Java 凭证探测使用的网关地址 | 容器内 `http://litellm:4000`；宿主机 `http://127.0.0.1:4000` | 否 | 无 | `application-service` 段 |
| `MODEL_GATEWAY_MASTER_KEY` | Java 探测鉴权密钥，须等于 `LITELLM_MASTER_KEY` | 与 `LITELLM_MASTER_KEY` 一致 | 探测功能必填 | 为空时探测返回 `UNAVAILABLE` | 同上 |
| `OPENAI_API_KEY` / `QWEN_API_KEY` / `VOLCENGINE_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` | MANAGED 流量中各 Provider 的平台密钥 | 留空表示不启用该 Provider | 按需 | 无 | `deploy/litellm/config.yaml` |

### 2.11 Agent 应用与运行时

| 变量 | 作用 | 默认值 / 示例 | 必填 | 生产 fail-fast | 证据 |
| --- | --- | --- | --- | --- | --- |
| `APP_NAME` | 服务标识 | `agent-service` | 否 | 无 | `config.py` L318 |
| `API_PREFIX` | 所有路由前缀（Nginx 剥 `/agent/` 后转发） | `/api/v1` | 否 | 无 | `config.py` L321；`docker-compose.yml` L184 |
| `STORAGE__BACKEND` | 会话持久化后端 | Compose `postgres`；`config.py` 默认 `memory` | 否 | **是**：`prod` 下必须为 `postgres` | `docker-compose.yml` L196；`config.py` L352-353 |
| `STORAGE__POSTGRES_URL` | 会话库连接串 | Compose 由 `AGENT_POSTGRES_*` 拼出 | `backend=postgres` 时必填 | **是**：`postgres` 但缺失连接串 → 启动失败 | `docker-compose.yml` L197；`config.py` L181-186 |
| `STORAGE__POOL_SIZE` | 连接池上限（1–50） | `5` | 否 | 无 | `config.py` L177 |
| `STORAGE__AUTO_SETUP` | 启动时幂等建表；无 DDL 权限的托管库设为 `false` 并手工迁移 | `true` | 否 | 无 | `config.py` L179 |
| `AGENT__CONTEXT_MAX_TOKENS` | 上下文预算，超出按完整消息单元从旧到新裁剪 | `6000` | 否 | 无 | `config.py` L264 |
| `AGENT__RECURSION_LIMIT` | 图执行步数上限（1–100） | `12` | 否 | 无 | `config.py` L266 |
| `AGENT__REQUEST_TIMEOUT_SECONDS` | 单次流总超时，超时下发 `error` 事件 | `120` | 否 | 无 | `config.py` L268 |
| `AGENT__THREAD_LOCK_TTL_SECONDS` | 同会话串行化锁持有时间 | `300` | 否 | 无 | `config.py` L270 |
| `AGENT__THREAD_LOCK_WAIT_SECONDS` | 抢锁等待窗口，`0` 表示立即 409 | `3` | 否 | 无 | `config.py` L272 |
| `AGENT__SSE_HEARTBEAT_SECONDS` | SSE 心跳注释行间隔 | `15` | 否 | 无 | `config.py` L274 |
| `AGENT__SYSTEM_PROMPT` | 提示词文件名（不含 `.md`，取自 `app/agent/prompts/`） | `pc-config-system` | 否 | 启动即校验文件存在，缺失抛 `RuntimeError` | `config.py` L280 |
| `AGENT__MAX_SOLVE_RETRIES` | 兼容性校验失败后自动重解次数（0–2），重解只放宽 `require_verified_offers` | `1` | 否 | 字段级范围校验 | `config.py` L282；`agent-service/.env.example` |
| `AGENT__PC_SELECTION_MODE` | PC 选型模式：`llm` 由 Build Architect 结构化选型；`solver` 为显式降级的确定性求解器 | `llm` | 否 | 字段级枚举校验（`solver` / `llm`） | `config.py` L284；`agent-service/.env.example` L119 |
| `AGENT__TOOL_TIMEOUT_SECONDS` | 工具默认超时 | `10` | 否 | 无 | `config.py` L278 |
| `AGENT__TOOL_MAX_RETRIES` | 工具失败重试次数（0–5） | `1` | 否 | 无 | `config.py` L280 |
| `AGENT__TOOL_MAX_OUTPUT_TOKENS` | 工具单次返回的 token 上限；超出后截断并附加提示 | `2000` | 否 | 字段级 `>0` | `config.py` L311 |
| `AGENT__TOOL_MAX_CALLS_PER_TURN` | 同一工具在一轮对话内的调用上限 | `3`（1–20） | 否 | 字段级范围校验 | `config.py` L313 |
| `AGENT__TOOL_REDACT_OUTPUT` | 工具返回给模型前是否脱敏（手机号、邮箱、身份证、API Key / Bearer） | `true` | 否 | 无 | `config.py` L315 |
| `AGENT__TOOL_MODULES` | 追加的工具模块（点分路径，逗号分隔）；内置与 `tools_ext` 无需声明 | 空 | 否 | 启动期逐个导入；模块不存在抛 `ToolModuleImportError`，工具重名抛 `ToolRegistrationError`，均阻止启动 | `config.py` L282 |
| `AGENT__HOOKS_MODULES` | 追加的生命周期钩子模块（点分路径，逗号分隔）；为空表示不启用任何钩子 | 空 | 否 | 启动期逐个导入；模块不存在抛 `HookModuleImportError`，阻止启动 | `config.py` L293；`agent-service/.env.example` L120 |
| `AGENT__SUMMARY_ENABLED` | 长会话摘要总开关；关闭时行为与接入前逐字节一致 | `false` | 否 | 无（摘要失败自动回退到普通裁剪） | `config.py` L301；`agent-service/.env.example` L122 |
| `AGENT__SUMMARY_TRIGGER_TOKENS` | 历史估算 token 超过该值才触发摘要（1–100000） | `5000` | 否 | 字段级范围校验 | `config.py` L302；`agent-service/.env.example` L123 |
| `AGENT__PROFILES_DIR` | Agent Profile 配置目录；相对路径按服务根目录解析 | `app/agents` | 否 | 启动期递归加载 `*.yaml`；目录不存在/为空、id 重复、提示词缺失、工具未注册均拒绝启动 | `config.py` L311 |
| `AGENT__DEFAULT_PROFILE` | 请求未携带 `agent_id` 时使用的 Profile | `pc-config` | 否 | 必须存在于 Profile 目录，否则启动失败 | `config.py` L319 |
| `AGENT__SESSION_INDEX_TTL_SECONDS` | **已废弃（2026-10-29）**，仅为兼容旧 `.env` 保留 | `2592000` | 否 | 无 | `config.py` L306 |
| `AGENT__SESSION_INDEX_MAX` | **已废弃（2026-10-29）**，同上 | `100` | 否 | 无 | `config.py` L308 |
| `HITL__ENABLED` | HITL 人在回路总开关；关闭时澄清与兼容性流程与接入前一致 | `false` | 否 | **是**：`true` 且 `STORAGE__BACKEND != postgres` 时启动失败（memory 不保存中断，无法恢复） | `config.py`（`HitlSettings` 与 `validate_hitl_storage`）；`docker-compose.yml` agent-service；`agent-service/.env.example` HITL 段 |
| `HITL__INTERRUPT_TTL_SECONDS` | 中断有效期；恢复时距 checkpoint 创建超过该值返回 `interrupt_expired` | `1800`（1–86400） | 否 | 字段级范围校验 | `config.py`（`HitlSettings`）；`app/api/v1/chat.py::_validate_resume` |
| `OPENUI__ENABLED` | 生成式 UI 总开关；关闭时系统提示词与接入前逐字节一致 | `false` | 否 | 无（无密钥依赖）；必须与前端 `VITE_OPENUI_ENABLED` 同步 | `config.py` L318-335；`docker-compose.yml` L215 |
| `OPENUI__PROMPT_NAME` | 组件契约文件名（不含 `.md`，取自 `app/agent/prompts/`） | `openui` | 否 | 字段级：名称白名单，禁止路径分隔符；文件缺失时首次对话抛错 | `config.py` L328；`agent-service/.env.example` L131 |
| `OPENUI__MAX_BLOCKS` | 单次回答的顶层 UI 块上限，写入提示词约束输出规模 | `4`（1–10） | 否 | 字段级范围校验 | `config.py` L335；`agent-service/.env.example` L133 |
| `MCP__ENABLED` | MCP 接入总开关；关闭时不导入 SDK、不建连、不发请求 | `false` | 否 | 无 | `config.py`（`MCPSettings`）；`agent-service/.env.example` MCP 段；`docker-compose.yml` agent-service |
| `MCP__GATEWAY_URL` | MCP 聚合端点覆盖值；留空则由 `LLM__GATEWAY_BASE_URL + /mcp` 推导 | 空 | 否 | 非 http(s) 只告警跳过 | `config.py`（`MCPSettings`）；`agent-service/.env.example` MCP 段 |
| `MCP__ALLOWED_TOOLS` | 只接入列出的工具（网关返回的原始工具名，JSON 数组）；为空表示全部 | `[]` | 否 | 无 | `config.py`（`MCPSettings`）；`agent-service/.env.example` MCP 段 |
| `MCP__CONNECT_TIMEOUT_SECONDS` | 建连 + initialize + `tools/list` 的总超时 | `10`（0 < t ≤ 60） | 否 | 字段级范围校验 | `config.py`（`MCPSettings`）；`agent-service/.env.example` MCP 段 |
| `MCP__REQUEST_TIMEOUT_SECONDS` | 单次 MCP 工具调用超时，作为治理超时传给注册表；必须大于 LiteLLM 侧 `mcp_servers.<name>.timeout` | `30`（0 < t ≤ 300） | 否 | 字段级范围校验 | `config.py`（`MCPSettings`）；`agent-service/.env.example` MCP 段 |
| `RAG__ENABLED` | 可选 RAG 总开关；关闭时不导入检索器模块、不发外部请求，行为与接入前一致 | `false` | 否 | 无；开启但 `RAG__RETRIEVER_MODULE` 为空或模块导入/工厂非法时拒绝启动 | `config.py` L372-381；`app/main.py` L145-150；`docker-compose.yml` L233-236 |
| `RAG__RETRIEVER_MODULE` | 检索器模块点分路径，模块必须暴露 `create_retriever()`，返回值需实现 `retrieve(request)` | 空 | `RAG__ENABLED=true` 时必填 | 启动期导入；缺模块、缺工厂、返回值非法均抛 `RagConfigError`，阻止启动 | `config.py` L380；`app/rag/registry.py`；`agent-service/.env.example` L157 |
| `RAG__TOP_K` | 单轮检索返回的引用条数上限 | `5`（1–20） | 否 | 字段级范围校验 | `config.py` L381；`agent-service/.env.example` L159 |
| `GUARD__ENABLED` | 输入侧护栏总开关；关闭后超长、控制字符、零宽字符与注入检测全部跳过 | `true` | 否 | 无 | `config.py`（`GuardSettings`）；`app/services/input_guard.py`；`docker-compose.yml` agent-service |
| `GUARD__MAX_INPUT_CHARS` | 单条用户输入字符上限；命中返回 422 `input_rejected` | `4000`（1–20000） | 否 | 字段级范围校验 | `config.py`（`GuardSettings`）；`agent-service/.env.example` 护栏段 |
| `GUARD__BLOCK_ON_INJECTION` | 是否拦截高置信度提示词注入；`false` 时只保留长度与字符类校验，用于灰度对比 | `true` | 否 | 无 | `config.py`（`GuardSettings`）；`app/services/input_guard.py` |
| `RATE_LIMIT__ENABLED` | 对话接口限流总开关 | `true` | 否 | 无 | `config.py`（`RateLimitSettings`）；`app/services/rate_limit.py` |
| `RATE_LIMIT__CHAT_PER_MINUTE` | 每用户窗口内允许的对话请求数；`0` 表示只保留配置位、不计数 | `20`（0–600） | 否 | 字段级范围校验 | `config.py`（`RateLimitSettings`）；`docker-compose.yml` agent-service |
| `RATE_LIMIT__WINDOW_SECONDS` | 固定窗口长度 | `60`（10–3600） | 否 | 字段级范围校验 | `config.py`（`RateLimitSettings`）；`agent-service/.env.example` 限流段 |
| `RATE_LIMIT__FAIL_OPEN` | Redis 不可用时是否放行；`true` 为降级放行，生产严格限流设为 `false`（返回 429） | `true` | 否 | 无 | `config.py`（`RateLimitSettings`）；`app/services/rate_limit.py` |

### 2.12 可观测

| 变量 | 作用 | 默认值 / 示例 | 必填 | 生产 fail-fast | 证据 |
| --- | --- | --- | --- | --- | --- |
| `METRICS__ENABLED` | 是否暴露 `{API_PREFIX}/metrics` | `true` | 否 | 无 | `config.py` L297 |
| `METRICS__TOKEN` | 应用内兜底令牌（16–128 字符），设置后必须带 `X-Metrics-Token` | 空（`.env.example` 注释） | 否 | 字段级长度校验 | `config.py` L298；`agent-service/.env.example` L128 |
| `LANGSMITH_TRACING` | LangSmith 追踪开关；开启后完整对话上报第三方 | 未设置（`.env.example` 注释） | 否 | 无 | `agent-service/.env.example` L131 |
| `LANGSMITH_API_KEY` / `LANGSMITH_PROJECT` / `LANGSMITH_ENDPOINT` | LangSmith 凭据与目标 | 未设置 | 否 | 无 | `agent-service/.env.example` L132-134 |

指标端点安全策略：Nginx 精确 location `= /agent/api/v1/metrics` 只放行回环与私网段（`frontend/deploy/nginx/default.conf.template`），`METRICS__TOKEN` 为兜底。

### 2.13 前端与管理端构建参数（构建期写死进静态产物）

| 变量 | 作用 | 默认值 / 示例 | 必填 | 生产校验 | 证据 |
| --- | --- | --- | --- | --- | --- |
| `VITE_APP_TITLE` | 用户端标题，注入 `index.html` | `Agent Analytics`（Compose）；`frontend/.env.example` 为 `Agent` | 是 | `pnpm check:env --mode production` 必填 | `docker-compose.yml` L284；`frontend/Dockerfile` L25 |
| `VITE_API_BASE_URL` | Java 接口基础地址，需含版本前缀 | `/api/v1` | 是 | 只允许以 `/` 开头或 `https://`；必填 | `docker-compose.yml` L285；`frontend/Dockerfile` L26 |
| `VITE_AGENT_BASE_URL` | Agent 接口基础地址 | `/agent/api/v1` | 否 | 同上规则 | `docker-compose.yml` L286；`frontend/Dockerfile` L27 |
| `VITE_APP_ENV` | 用户端构建环境 | Compose 固定 `production` | 是 | 只允许 `production` | `docker-compose.yml` L283；`frontend/Dockerfile` L24 |
| `VITE_API_TIMEOUT` | 用户端请求超时（毫秒） | Compose 固定 `10000` | 否 | 必须是正整数 | `docker-compose.yml` L287；`frontend/Dockerfile` L28 |
| `VITE_USE_MOCK` | 用户端是否启用 Mock | Compose 固定 `false` | 否 | 生产必须不为 `true` | `docker-compose.yml` L288；`frontend/Dockerfile` L29 |
| `VITE_OPENUI_ENABLED` | 用户端生成式 UI 开关 | `false` | 否 | 无强制校验；默认关闭，关闭时不加载 OpenUI 运行时；必须与 `OPENUI__ENABLED` 同步 | `docker-compose.yml` L290；`frontend/Dockerfile` L31；`frontend/src/shared/lib/env.ts` |
| `ADMIN_APP_TITLE` | 管理端标题（根 `.env` 名） | `Agent 管理后台` | 否 | 由 Compose 映射为 `VITE_APP_TITLE` build arg | `docker-compose.yml` L254；根 `.env.example` |
| `VITE_BASE_PATH` | 管理端部署前缀 | Compose 固定 `/admin/`；`admin/.env.example` 为 `/` | 否 | 必须以 `/` 开头；与 Nginx `/admin/` 前缀一致 | `admin/Dockerfile`；`admin/src/lib/env.ts` |

`VITE_*` 变量名禁止出现密钥类词根（`VITE_API_KEY`、`VITE_JWT_SECRET` 会被 `frontend/scripts/check-env.mjs` 拒绝）。CI 与镜像构建都在 `vite build` 之前跑 `pnpm check:env --mode production`，错误配置会让构建直接失败。

管理端没有独立的 `check:env` 脚本：`VITE_BASE_PATH` 同时被 `admin/vite.config.ts` 用作 Vite `base`、被 `admin/src/lib/env.ts` 用作 Router `basepath`，两者必须与 frontend Nginx 的 `/admin/` 前缀一致，否则资源 404 或深层链接无法匹配。

---

## 3. 各端读取方式与命名映射

### 3.1 Java（`application*.yaml` + 环境变量）

- 所有可配置项写在 `application.yaml` 的 `${VAR:default}` 占位符里，按 profile 覆盖：`application-local.yaml`、`application-dev.yaml`、`application-prod.yaml`、`application-test.yaml`。
- 默认 profile 是 `local`（`application.yaml` L5）；Compose 显式传 `SPRING_PROFILES_ACTIVE=prod`。
- Spring 的 relaxed binding 让 `JWT_PRIVATE_KEY` → `app.security.jwt.private-key` 之类的映射自动成立，代码里不出现环境变量名。
- 数据库连接串按 profile 拆分：`local` 有默认值，`prod` 无默认值（`application-prod.yaml` L3-5）。
- 非 profile 变量（模型运行时、CORS、引导账号）集中在 `application.yaml`，默认值即代码默认值。

### 3.2 Agent（Pydantic Settings，双下划线嵌套）

- 唯一来源是 `agent-service/app/core/config.py` 的 `Settings`；业务代码只经 `get_settings()` 读取，禁止散落 `os.getenv`。
- 嵌套分隔符为 `__`：`LLM__MODEL` → `settings.llm.model`，`AUTH__JWT_PUBLIC_KEY` → `settings.auth.jwt_public_key`。
- 优先级：真实环境变量 > `.env` > 字段默认值；`.env` 路径固定在 `agent-service/.env`（`parents[2]`），与启动目录无关。
- `case_sensitive=False`、`extra="ignore"`：**拼错或废弃的变量不会报错，只会静默失效**（见 §6 A-02）。
- 启动即校验：类型错误、缺失必填、跨字段矛盾在进程启动时抛 `ValidationError`，不会拖到某个接口才失败。

### 3.3 前端（`VITE_*` 构建期注入）

- 只允许通过 `frontend/src/shared/lib/env.ts` 读取，业务代码不直接访问 `import.meta.env`。
- 变量在 `docker build` 阶段以 build args 注入（`docker-compose.yml` 的 `frontend.build.args`），写进静态产物；**变更后必须重建镜像，只重启容器无效**。
- 本地开发用 `frontend/.env.example` 复制为 `.env.local`。

### 3.4 根变量 → 服务内部变量映射

Compose 是两侧命名的唯一桥接层，映射关系全部在 `docker-compose.yml` 中显式书写：

| 根 / Compose 变量 | Java 侧 | Agent 侧 | 证据 |
| --- | --- | --- | --- |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `DB_USERNAME` / `DB_PASSWORD` / `DB_URL` 的组成部分 | 不使用（Agent 有独立库） | `docker-compose.yml` L112-114 |
| `AGENT_POSTGRES_USER` / `AGENT_POSTGRES_PASSWORD` / `AGENT_POSTGRES_DB` | 不使用 | 拼成 `STORAGE__POSTGRES_URL` | `docker-compose.yml` L197 |
| `REDIS_PASSWORD` | 不使用 | 拼成 `REDIS__URL` | `docker-compose.yml` L201 |
| `JWT_PRIVATE_KEY` | `JWT_PRIVATE_KEY`（同名透传） | **不下发**（Agent 无签名能力） | `docker-compose.yml` L116 |
| `JWT_PUBLIC_KEY` | `JWT_PUBLIC_KEY` | `AUTH__JWT_PUBLIC_KEY` | `docker-compose.yml` L117、L188 |
| `JWT_KID` | `JWT_KID` | `AUTH__JWT_KID` | `docker-compose.yml` L118、L190 |
| `JWT_ISSUER` | `JWT_ISSUER` | `AUTH__ISSUER` | `docker-compose.yml` L119、L192 |
| `JWT_AUDIENCE` | `JWT_AUDIENCE` | `AUTH__AUDIENCE` | `docker-compose.yml` L120、L194 |
| `MODEL_RUNTIME_ENABLED` | `MODEL_RUNTIME_ENABLED` | `MODEL_RUNTIME__ENABLED` | `docker-compose.yml` L137、L213 |
| `INTERNAL_AUTH_CLIENT_ID` | `INTERNAL_AUTH_CLIENT_ID` | `CONTROL_PLANE__CLIENT_ID` | `docker-compose.yml` L143、L219 |
| `INTERNAL_AUTH_CLIENT_SECRET` | `INTERNAL_AUTH_CLIENT_SECRET` | `CONTROL_PLANE__CLIENT_SECRET` | `docker-compose.yml` L144、L220 |
| `LLM_API_KEY` | 不使用 | `LLM__API_KEY` | `docker-compose.yml` L206 |
| `LLM_MODEL` | 不使用 | `LLM__MODEL` | `docker-compose.yml` L205 |
| `LLM_BASE_URL` | 不使用 | `LLM__BASE_URL` | `docker-compose.yml` L207 |
| `LLM_MAX_TOKENS` | 不使用 | `LLM__MAX_TOKENS` | `docker-compose.yml` L211 |
| `OPENUI_ENABLED` | 不使用 | `OPENUI__ENABLED` | `docker-compose.yml` L215 |
| `HITL_ENABLED` | 不使用 | `HITL__ENABLED` | `docker-compose.yml` agent-service |
| `HITL_INTERRUPT_TTL_SECONDS` | 不使用 | `HITL__INTERRUPT_TTL_SECONDS` | `docker-compose.yml` agent-service |
| `RAG_ENABLED` | 不使用 | `RAG__ENABLED` | `docker-compose.yml` L234 |
| `RAG_RETRIEVER_MODULE` | 不使用 | `RAG__RETRIEVER_MODULE` | `docker-compose.yml` L235 |
| `RAG_TOP_K` | 不使用 | `RAG__TOP_K` | `docker-compose.yml` L236 |
| `GUARD_ENABLED` / `GUARD_MAX_INPUT_CHARS` / `GUARD_BLOCK_ON_INJECTION` | 不使用 | `GUARD__*` | `docker-compose.yml` agent-service |
| `RATE_LIMIT_ENABLED` / `RATE_LIMIT_CHAT_PER_MINUTE` / `RATE_LIMIT_WINDOW_SECONDS` / `RATE_LIMIT_FAIL_OPEN` | 不使用 | `RATE_LIMIT__*` | `docker-compose.yml` agent-service |
| `VITE_APP_TITLE` / `VITE_API_BASE_URL` / `VITE_AGENT_BASE_URL` | — | — | 前端 build args，`docker-compose.yml` L284-286 |
| `VITE_OPENUI_ENABLED` | — | — | 前端 build args，`docker-compose.yml` L290；必须与 `OPENUI_ENABLED` 同步 |
| `ADMIN_APP_TITLE` | — | — | 管理端标题，映射为 `VITE_APP_TITLE` build arg，`docker-compose.yml` L254 |

**本地脱离 Compose 启动时**这套映射不再生效：Java 读 `DB_*`、`JWT_*` 原名；Agent 要按 `agent-service/.env.example` 写 `AUTH__*`、`STORAGE__*`、`LLM__*` 原名。只把根 `.env` 复制进 `agent-service/` 是不够的——两份文件的键名不同。注意 `STORAGE__POSTGRES_URL` 的地址随运行位置不同：宿主机本地开发用 `127.0.0.1:5433`（pgvector 的宿主映射），容器内由 Compose 注入 `pgvector:5432`。

### 3.5 差异与未消费项

| 项 | 事实 | 影响 |
| --- | --- | --- |
| `deploy/.env.example` 的 `MINIO_*` | 2026-11-01 已从该文件删除：全仓无 MinIO 服务，也无任何客户端读取 | 已解决（EV-02）；新增对象存储前先补服务与消费方，不要提前登记变量 |
| `LLM_BASE_URL` 根侧留空 | Compose 用 `${LLM_BASE_URL:-https://api.deepseek.com/v1}` 兜底，只影响未配置网关时的直连模式 | 网关模式下该值不参与调用；切换模型只需改 `LLM_MODEL` 与 `MODEL_DEFAULT_KEY` |
| `CORS_ORIGINS` 容器内固定 | Compose 写死 `'["http://localhost"]'`，不使用根 `.env` 的同名项 | 同源部署无影响；分离部署时需改 `docker-compose.yml`（属配置变更） |
| `APP_ENV` 双默认 | 根 `.env.example` 无此项，Compose 默认 `prod`，`agent-service/.env.example` 默认 `dev` | 容器默认生产校验；本地直接 `uv run` 时是 `dev` |
| `DEBUG` 双默认 | Compose 固定 `"false"`；Agent `.env.example` 为 `true` | 同上 |
| OpenUI 双端开关 | `VITE_OPENUI_ENABLED` 与 `OPENUI__ENABLED` 各自独立，无启动期比对 | 发布时必须同时设为 `true`：只开前端会拿到纯文本（渲染为空），只开 Agent 会让 OpenUI 内容退化为原始代码块 |
| `application-service/.env.example` | 只有 `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`，服务于该服务自带 Compose | 与 Java 运行时 `DB_*` / `JWT_*` 不是一套 |

---

## 4. 生产 fail-fast 清单

### 4.1 Java：`ProdConfigGuard`（`spring.profiles.active=prod` 时，在容器 refresh 之前终止启动）

实现位于 `application-service/src/main/java/com/example/agent/shared/config/ProdConfigGuard.java`，通过 `META-INF/spring.factories` 注册为 `ApplicationContextInitializer`，执行早于 Bean 初始化、数据库连接与 Tomcat 启动。

| # | 拒绝条件 | 证据 |
| --- | --- | --- |
| 1 | `debug=true` | `ProdConfigGuard.java` L69-71 |
| 2 | `JWT_PRIVATE_KEY` 为空、未解析占位符、或不是合法 PKCS#8 PEM | 同上 L112-122 |
| 3 | `JWT_PUBLIC_KEY` 为空、未解析占位符、或不是合法 X.509 PEM | 同上 L124-134 |
| 4 | 私钥与公钥模数不一致（不是一对） | 同上 L106-110 |
| 5 | `JWT_AUDIENCE` 为空或仍是占位符 | 同上 L149-154 |
| 6 | `AUTH_COOKIE_SECURE` 不为 `true` | 同上 L162-167 |
| 7 | `DB_URL`（`spring.datasource.url`）为空或未解析 | 同上 L169-174 |
| 8 | `DB_PASSWORD` 为空、未解析，或命中默认占位词（`postgres`、`password`、`change-me`、`replace-with` 等） | 同上 L176-189、L43-48 |
| 9 | 开启模型运行时后，`INTERNAL_AUTH_CLIENT_SECRET` 为空、占位，或长度 < 16 | 同上 L197-210 |

错误信息一次收集全部问题，只报属性名与原因，不打印真实值。占位词匹配规则为「完全相等」或「词根后紧跟非字母字符」，因此 `my-secret-2026-...` 不会被误伤。

另有启动期 Bean Validation（非法时同样拒绝启动，与 profile 无关）：

- `BYOK_ENABLED=true` 时必须同时开启 `MODEL_RUNTIME_ENABLED` 且主密钥可用（`ModelRuntimeProperties.java` L92-98）。
- 开启模型运行时后 `INTERNAL_AUTH_CLIENT_SECRET` 不能为空（同上 L75-82）。
- `MODEL_QUOTA_DAILY_REQUESTS ≥ 1`、`MODEL_RECONCILE_CRON` 非空（同上 L105、L123）。

### 4.2 Agent：`Settings.validate_production_settings`（仅 `APP_ENV=prod`）

| # | 拒绝条件 | 证据 |
| --- | --- | --- |
| 1 | `DEBUG=true` | `config.py` L346-347 |
| 2 | `AUTH__JWT_PUBLIC_KEY` 含 `replace-with` / `change-me` / `your-secret` 占位片段 | 同上 L348-351 |
| 3 | `STORAGE__BACKEND != postgres` | 同上 L352-353 |
| 4 | `CORS_ORIGINS` 含 `*` | 同上 L354-355 |
| 5 | `LLM__API_KEY` 以 `sk-replace` 开头 | 同上 L356-360 |
| 6 | `REDIS__URL` 为空，或 `REDIS__REQUIRED != true` | 同上 L361-362 |
| 7 | `MODEL_RUNTIME__ENABLED=true` 但 `CONTROL_PLANE__CLIENT_SECRET` 缺失或仍是占位值 | 同上 L363-374 |

另有字段级/模型级校验，**任何环境**启动即生效：`AUTH__JWT_PUBLIC_KEY` 必须可解析为 PEM 且非空；`AUTH__JWT_ALGORITHM` 只接受 `RS256`；`AUTH__AUDIENCE` 不能为空字符串；`STORAGE__BACKEND=postgres` 必须给 `STORAGE__POSTGRES_URL`；`REDIS__REQUIRED=true` 必须给 `REDIS__URL`；`REDIS__KEY_PREFIX` 不含冒号；`CONTROL_PLANE__BASE_URL` 必须是 http(s)；`METRICS__TOKEN` 长度 16–128；`OPENUI__PROMPT_NAME` 只允许小写字母、数字与连字符，`OPENUI__MAX_BLOCKS` 限制在 1–10（`config.py` L78-235、L269-298）。

### 4.3 校验之外、必须靠人工的项

| 项 | 缺口 | 建议 |
| --- | --- | --- |
| `JWT_KID` / `JWT_ISSUER` / `AUTH__JWT_KID` / `AUTH__ISSUER` 两端一致 | 两侧都无启动期比对 | 发布检查清单逐项核对（见 `docs/deployment/deployment-guide.md` §8） |
| `INTERNAL_AUTH_CLIENT_ID` / `CONTROL_PLANE__CLIENT_ID` 一致 | 同上 | 同上 |
| `AUTH_ADMIN_PASSWORD` 强度 | `ProdConfigGuard` 只校验数据库口令，不校验引导账号口令 | 上线前人工确认；生产可留空不播种 |
| `CORS_ALLOWED_ORIGINS` 白名单 | 无启动期校验（代码层无通配保护） | 生产显式填写域名，不使用通配 |
| `MODEL_CRED_MASTER_KEY` 与备份分离保管 | 无校验 | 丢失主密钥等于全部已存凭证不可用 |

---

## 5. 密钥生成与轮换

### 5.1 RSA 密钥对（JWT）

```bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out jwt-private.pem
openssl rsa -in jwt-private.pem -pubout -out jwt-public.pem
```

写入 `.env` 时把 PEM 压成单行、换行写成字面量 `\n`；Java 的 `JwtKeyLoader` 与 Agent 的 `config.py`（`PEM_NEWLINE_ESCAPE`）都会还原：

```text
JWT_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nMIIEv...\n-----END PRIVATE KEY-----"
JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\nMIIBIj...\n-----END PUBLIC KEY-----"
```

私钥只注入 Java；公钥同时注入 Java 与 Agent（Agent 侧名为 `AUTH__JWT_PUBLIC_KEY`）。公钥可公开，私钥必须只存在于服务器密钥管理或 `.env`，禁止提交、禁止进镜像。

### 5.2 `JWT_KID` 轮换

1. 生成新密钥对，给它新的 `JWT_KID`。
2. 先用**同一把**新私钥/公钥 + 新 kid 同时更新 Java 与 Agent 的两组变量（Java 的 `JWT_` 前缀项与 Agent 的 `AUTH__` 前缀同名项，如 `AUTH__JWT_PUBLIC_KEY`、`AUTH__JWT_KID`，见 §2.4），再重启两侧。
3. 现有实现按 kid 从「本进程公钥白名单」选钥，未知 kid 直接 401，**不支持双 kid 并行验签**；因此轮换窗口内旧令牌会全部失效，需重新登录。仓库中存在过的 `JWT_PREVIOUS_PUBLIC_KEY` 只是历史预留键，代码未读取（`scripts/check-env-docs.ps1` 白名单有注释）。
4. 轮换后作废旧私钥，检查签发与验签两侧 `kid`、`iss`、`aud` 完全一致。

### 5.3 BYOK 主密钥环

```bash
openssl rand -base64 32   # 生成 32 字节 base64 主密钥
```

- 单密钥：`MODEL_CRED_MASTER_KEY=<base64>`，新密文版本由 `MODEL_CRED_KEY_VERSION` 指定。
- 轮换：把旧密钥与新密钥按 `<version>:<base64>` 写进 `MODEL_CRED_MASTER_KEYS`（英文逗号分隔），把 `MODEL_CRED_KEY_VERSION` 递增到新版本；旧版本密文仍可解密（`ModelRuntimeProperties.java` L220-232）。
- 只注入 Java，禁止下发 Agent 或前端；`MODEL_CRED_MASTER_KEYS` 未配置时按单密钥回退，且必须包含当前 `MODEL_CRED_KEY_VERSION`。

### 5.4 口令与连接串

- 数据库、Redis、引导账号、`INTERNAL_AUTH_CLIENT_SECRET` 都必须替换 `.env.example` 中的 `replace-with-*` 占位值；`ProdConfigGuard` 会拒绝占位词。
- `INTERNAL_AUTH_CLIENT_SECRET` 在开启模型运行时后必须 ≥ 16 字符（`ProdConfigGuard.java` L32）。
- Redis 口令会拼进 `redis://` 连接串，含 `@ : / #` 等字符时必须 URL 编码，否则连接串解析失败。

---

## 6. 已知缺陷与待确认

| 编号 | 问题 | 证据 | 影响 / 处理 |
| --- | --- | --- | --- |
| A-02 | Agent `Settings` 使用 `extra="ignore"`，拼错或废弃的变量静默失效 | `config.py` L314 | 与「启动即校验」的设计目标相悖；`AUTH__JWT_ISSUER`、`AUTH__JWT_SECRET` 等历史键残留时既不报错也不生效。是否改 `extra="forbid"` **待评估** |
| EV-01 | 多 Provider 默认地址与探测模型曾由环境变量配置，Agent 侧缺少对应键 | 历史问题 | **已关闭（ADR 0008）**：配置移交 LiteLLM（`deploy/litellm/config.yaml`），两侧不再存在该变量；`scripts/check-env-docs.ps1` 通过 |
| EV-02 | `deploy/.env.example` 残留 `MINIO_*` 三个键，无对应服务 | 全仓扫描仅命中该文件 | **已解决（2026-11-01）**：三个键已删除；全仓无消费方 |
| EV-03 | 数据库宿主机端口覆盖变量未收录进任何 `.env.example` | `docker-compose.yml` L32、L59 | 改端口只能直接改 `docker-compose.yml`；本文为避免出现未登记键，未列其全名 |
| EV-04 | Agent 容器内 `CORS_ORIGINS` 与 `APP_ENV`、`DEBUG` 由 Compose 固定/默认，不读根 `.env` | `docker-compose.yml` L182-186 | 分离部署需改 Compose；本文如实标注默认值 |
| EV-05 | `AUTH__DEV_PRIVATE_KEY` 若误注入生产，`/auth/dev-token` 具备签发能力 | `config.py` L73；服务文档 §11 | 接口本身受 `APP_ENV=dev` 且 `DEBUG=true` 双重限制，生产禁止注入 |

---

## 7. 变更规则

新增、改名或删除一个环境变量时，按顺序完成五步，缺一步即视为未完成：

1. 服务 `.env.example`（`agent-service/.env.example`、`application-service/.env.example`、`frontend/.env.example`）；
2. 根 `.env.example`（Compose 注入名）；
3. `docker-compose.yml` / `deploy/docker-compose.infra.yml` 的注入或透传；
4. 本文件（变量总表对应分组 + 必要的 fail-fast 说明）；
5. `docs/deployment/deployment-guide.md`（仅当影响启动/发布步骤时）。

其他约束：

- 变量名使用大写下划线；Agent 内部嵌套用 `__`，根与 Compose 层保持扁平，映射一律在 Compose 中显式书写。
- 不得在文档、注释、提交信息中写入真实密钥、口令、Token 或内网地址；示例值统一用 `replace-with-*`。
- 生产缺关键变量必须 fail-fast，不接受「带病启动 + 日志告警」。
- 修改 `.env.example` 时同步检查 `scripts/check-env-docs.ps1` 是否会把新键判为缺失。

---

## 8. 校验命令

```powershell
# 文档里出现的环境变量键必须存在于某个 .env.example
powershell -NoProfile -File scripts/check-env-docs.ps1

# 文档相对链接有效性
powershell -NoProfile -File scripts/check-doc-links.ps1

# Compose 变量插值与语法（缺变量会在此步报错）
Copy-Item .env.example .env
docker compose --env-file .env config -q

# 前端构建期硬校验
corepack pnpm --dir frontend check:env --mode production
```

已知基线：治理前 `check-env-docs.ps1` 会因 §6 EV-01 报 4 处缺失（均指向 Agent 侧多 provider 地址键），与本次新增文档无关；修复需在 `agent-service/.env.example` 补登该键。
