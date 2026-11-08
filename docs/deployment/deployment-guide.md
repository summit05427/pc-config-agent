# 部署指南

| 属性 | 内容 |
| --- | --- |
| 状态 | Current |
| 最后核验 | 2026-11-04 |
| 权威性 | Authoritative（部署流程、启动命令、Nginx 路由、CI 门禁、发布与回滚的唯一入口） |
| 主要证据 | `docker-compose.yml`、`deploy/docker-compose.infra.yml`、`frontend/deploy/nginx/default.conf.template`、`admin/deploy/nginx/default.conf`、`.github/workflows/ci.yml`、四份 `Dockerfile`、各服务 `README.md`、`scripts/*.ps1`、`scripts/dev/*.ps1` |
| 环境变量 | 本文**不复制变量表**，全部见 [`environment-variables.md`](environment-variables.md) |

---

## 1. 环境要求与前置

| 组件 | 要求 | 依据 |
| --- | --- | --- |
| Node.js | `^22.18.0` 或 `>=24.12.0` | `frontend/README.md`；`frontend/Dockerfile` 用 `node:24-alpine` |
| pnpm | `10.18.0`，统一用 `corepack pnpm`，不要用全局 pnpm | `frontend/Dockerfile` L8（`corepack prepare pnpm@10.18.0`） |
| JDK | 21 | `.github/workflows/ci.yml` `backend` Job；`application-service/Dockerfile` 用 `eclipse-temurin-21` |
| Python | 3.12 | `agent-service/pyproject.toml`；CI `agent` Job |
| uv | 用于 Agent 依赖安装与命令执行 | `agent-service/README.md`；CI `astral-sh/setup-uv` |
| Docker | 需启用 BuildKit（三份 Dockerfile 首行为 `# syntax=docker/dockerfile:1.7`） | `frontend/Dockerfile`、`application-service/Dockerfile` |
| Docker Compose | v2（Compose 用到 `${VAR:?message}` 与 `depends_on.condition`） | `docker-compose.yml` L9、L156 |
| OpenSSL | 生成 RSA 密钥对与 base64 主密钥 | `根 .env.example` L26-27、L69 |

首次准备：

```bash
cp .env.example .env      # 然后替换所有 replace-with-* （见 environment-variables.md）
```

`.env` 只存在于部署机，`.gitignore` 已排除；仓库只提交 `.env.example`。

---

## 2. 本地启动（四端在宿主机跑，容器只跑中间件）

开发阶段为强制方式：`frontend`、`admin`、`application-service`、`agent-service` 全部在宿主机启动，容器只跑 `postgres`、`pgvector`、`redis`（规则见 `.trae/rules/00-monorepo-common.md` §2.1）。

### 2.1 一键启动（推荐）

`scripts/dev/start-local.ps1` 会读取根 `.env`、启动中间件、校验数据库口令，然后并行拉起四端：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start-local.ps1
```

管理端单独启动（默认启动范围不含管理端）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start-local.ps1 -Service admin -SkipMiddleware
```

停止四端（默认保留中间件与数据卷）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/stop-local.ps1
```

- 默认 `-Service all` 只拉起 `application`、`agent`、`frontend`；管理端采取独立启动策略，需显式执行 `-Service admin`。
- `-Service application|agent|frontend|admin` 只操作单端；`-SkipMiddleware` 跳过中间件。
- 端口已占用时自动跳过，不会重复启动。
- 日志写入 `logs/dev/*.log`；`logs/` 已被 `.gitignore` 排除。
- 启动 Java 前会用容器网络（`scram-sha-256`）真实校验 `POSTGRES_PASSWORD`，口令不一致时直接给出提示，不让 Flyway 报错掩盖根因。
- 启动前会先执行 `scripts/dev/preflight.ps1`，比对根 `.env`、`agent-service/.env`、`frontend/.env` 之间的契约型配置，存在阻断项时中止启动。
- 脚本只做进程编排，不替代下面的手工命令；需要理解每一步时按 2.2–2.6 操作。

预检可以单独执行，适合部署前或 CI 中调用（存在阻断项时退出码为 1）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/preflight.ps1
```

预检覆盖的范围：

- `COMPOSE_PROJECT_NAME` 合法性与 `IMAGE_PREFIX` 是否仍为模板默认值（防止与同机其它项目共用容器、卷、镜像）
- 八个宿主端口是否互不重复，并提示已被占用的端口
- JWT KID 与公钥在根 `.env` 和 `agent-service/.env` 中是否一致（不一致会导致 Agent 验签失败，前端把 401 当登录失效）
- `MODEL_RUNTIME_ENABLED` 与 Agent 的 `MODEL_RUNTIME__ENABLED` 是否一致；`BYOK_ENABLED` 开启时 `MODEL_CRED_MASTER_KEY` 是否为 32 字节 base64
- `MODEL_GATEWAY_MASTER_KEY` 是否与 `LITELLM_MASTER_KEY` 一致
- OpenUI 开关在根 `.env`、`agent-service/.env`、`frontend/.env` 中是否同步
- `LLM_API_KEY` 是否仍为空、过短或示例值（仅告警，BYOK 场景可接受）

### 2.2 启动基础设施

```bash
docker compose --env-file .env up -d postgres pgvector redis
```

只启动三个中间件，复用根 `docker-compose.yml` 的数据卷（`postgres_data`、`agent_pg_data`、`redis_data`）。不要用不带服务名的 `docker compose up -d`：那会连带启动四端容器。宿主机端口分别为 `5432`、`5433`、`6379`，均只绑 `127.0.0.1`（`docker-compose.yml` L32、L59、L85）。

若之前启动过整栈，先停四端容器：

```bash
docker compose stop frontend admin application-service agent-service
```

`deploy/docker-compose.infra.yml` 使用独立的 `infra_*` 数据卷，与本套中间件数据不互认，日常开发不要混用。

### 2.3 前端与管理端

```bash
corepack pnpm --dir frontend install
cp frontend/.env.example frontend/.env.local     # 按本地后端地址改 VITE_API_BASE_URL
corepack pnpm --dir frontend dev                 # Vite 开发服务器，端口 5273

corepack pnpm --dir admin install
cp admin/.env.example admin/.env                 # VITE_BASE_PATH 保持 /
corepack pnpm --dir admin dev                    # 端口 5274，/api 代理到 18080
```

### 2.4 Java（`application-service/`）

推荐直接用脚本（从根 `.env` 注入全部变量，并在启动前校验数据库口令）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start-local.ps1 -Service application
```

手工启动时，`local` profile 只声明 `${DB_PASSWORD}` 占位符、没有默认值，必须由启动者注入，且必须与数据库实际口令一致：

```powershell
$env:SPRING_PROFILES_ACTIVE="local"
$env:DB_USERNAME="agent"
$env:DB_PASSWORD="<根 .env 的 POSTGRES_PASSWORD>"
$env:JWT_PRIVATE_KEY=(Get-Content jwt-private.pem -Raw)
$env:JWT_PUBLIC_KEY=(Get-Content jwt-public.pem -Raw)
$env:AUTH_ADMIN_PASSWORD="<根 .env 的 AUTH_ADMIN_PASSWORD>"
.\mvnw.cmd spring-boot:run
```

```bash
# Linux/macOS
DB_PASSWORD="<根 .env 的 POSTGRES_PASSWORD>" JWT_PRIVATE_KEY="$(cat jwt-private.pem)" JWT_PUBLIC_KEY="$(cat jwt-public.pem)" \
  AUTH_ADMIN_PASSWORD="<根 .env 的 AUTH_ADMIN_PASSWORD>" ./mvnw spring-boot:run
```

> 口令一致性：`POSTGRES_PASSWORD` 只在数据卷首次初始化时写入数据库，之后修改根 `.env` 不会改变已有角色口令。若报 `password authentication failed for user "agent"`，优先用脚本启动（脚本会预检并给出明确提示）；确需更换口令时，先在库里 `ALTER ROLE`，再同步根 `.env`。不要用 `application-service/.env.example` 中的 `change-me` 作为实际口令。

- 默认 `local` profile，端口 `8080`；`local` 的 `DB_URL` 默认 `jdbc:postgresql://localhost:5432/agent`（`application-local.yaml` L3）。
- `local` profile 默认放开 `http://localhost:5173` 跨域，便于前端直连。
- 启动后 `/swagger-ui.html`、`/v3/api-docs`、`/actuator/health` 可用；首次启动由 Flyway 建表并播种引导账号。

### 2.5 Agent（`agent-service/`）

```powershell
uv sync --frozen
Copy-Item .env.example .env      # 至少改 LLM__API_KEY、AUTH__JWT_PUBLIC_KEY、STORAGE__*
uv run python run.py             # Windows 必须用 run.py
```

```bash
# Linux/macOS
uv run uvicorn app.main:app --reload --port 8000
```

Windows 必须用 `run.py`：它把事件循环切换为 Selector，否则 psycopg 异步驱动在 ProactorEventLoop 下报错（`agent-service/README.md`）。

> **本地端口注意**：`agent-service/.env.example` 的 `STORAGE__POSTGRES_URL` 示例已改为 `127.0.0.1:5433/agent_service`（2026-11-01 修正），与根 Compose 的中间件宿主机映射一致。Agent 不得连 Java 的 `agent` 库；容器内由 Compose 注入 `pgvector:5432`。
>
> 另注：`AUTH__JWT_PUBLIC_KEY`、`AUTH__JWT_KID`、`AUTH__ISSUER`、`AUTH__AUDIENCE` 四项必须与 Java 完全一致，否则所有令牌 401。开发令牌接口 `/api/v1/auth/dev-token` 仅在 `APP_ENV=dev` 且 `DEBUG=true` 时可用。

### 2.6 登录与联调

用 `AUTH_ADMIN_USERNAME` / `AUTH_ADMIN_PASSWORD` 登录（前端 `frontend/README.md`）。前端经 Nginx 或本地 Vite 代理（`/api` → 18080、`/agent` → 18000）访问后端；只有需要绕过代理时才把 `VITE_AGENT_BASE_URL` 改为 `http://localhost:18000/api/v1`，此时属于跨源，`/auth/refresh` 依赖的 HttpOnly Cookie 不会生效，刷新页面即掉登录。

---

## 3. 全栈 Compose 启动

四端容器只用于发布前验收或验证 Nginx / 代理链路；日常开发按第 2 节在宿主机启动。整栈与中间件都通过 Compose profile 显式启用，命令里必须带 `--profile full`（或 `--profile infra`）。

### 3.1 服务与端口

| 服务 | 镜像 | 容器内端口 | 宿主机端口 | 依赖 | 健康检查 |
| --- | --- | --- | --- | --- | --- |
| `postgres` | `postgres:18-alpine` | 5432 | `127.0.0.1:5432` | — | `pg_isready` |
| `pgvector` | `pgvector/pgvector:pg18` | 5432 | `127.0.0.1:5433` | — | `pg_isready` |
| `redis` | `redis:8-alpine` | 6379 | `127.0.0.1:6379` | — | `redis-cli ping` |
| `application-service` | `agent/application-service:local`（本地构建） | 8080 | `127.0.0.1:8080` | `postgres` healthy | `/actuator/health` 含 `"status":"UP"` |
| `agent-service` | `agent/agent-service:local`（本地构建） | 8000 | `127.0.0.1:8000` | `pgvector` healthy、`redis` healthy | `/api/v1/health/ready` 返回 200 |
| `admin` | `agent/admin:local`（本地构建） | 80 | 不映射（经 `frontend` 的 `/admin/`） | — | `/healthz` 返回 `ok` |
| `frontend` | `agent/frontend:local`（本地构建） | 80 | `WEB_PORT`（默认 80） | `application-service` healthy、`agent-service` started、`admin` started | `/healthz` 返回 `ok` |

启动顺序由 `depends_on` + `healthcheck` 决定；`frontend` 对 Agent 只要求 `service_started`，因此 Agent 就绪前访问 `/agent/` 可能短暂 502。`admin` 是纯静态站点，无外部依赖。

profile 归属：`postgres`、`pgvector`、`redis` 同时属于 `infra` 与 `full`；`application-service`、`admin`、`frontend` 只属于 `full`；`agent-service` **不带 profile**，因此默认可用（Solo 依赖这一点）。不带 `--profile` 的 `docker compose up -d` 只会启动 `agent-service`。

### 3.2 启动、查看、停止

```bash
docker compose --profile full --env-file .env up -d --build
docker compose --profile full ps
docker compose --profile full logs -f application-service
docker compose --profile full logs -f agent-service
docker compose --profile full down          # 保留数据卷
docker compose --profile full down -v       # 删除数据卷，谨慎
```

- `--env-file .env` 可省略：Compose 默认读取工作目录的 `.env`；显式指定时路径以仓库根为准。
- 缺变量时 Compose 用 `${VAR:?message}` 直接报错（例：`POSTGRES_PASSWORD is required`），不会带着空口令启动。
- 只改运行时环境变量（数据库、JWT、LLM、Redis）**不需要 `--build`**；改 `VITE_*`、源码或 Dockerfile **必须** `--build` 对应服务。
- 只跑中间件时可直接点名服务（`docker compose --env-file .env up -d postgres pgvector redis`，见 §2.2），显式点名会忽略 profile 限制。

### 3.3 Solo 模式（只启动 Agent）

只跑一个 Agent 容器（memory 存储、无 Redis、无需中间件），用于模板演示与 Agent 单点联调。完整步骤、dev-token、curl 示例与能力边界见 [solo-mode.md](solo-mode.md)。

```bash
uv --directory agent-service run python ../scripts/generate_solo_env.py   # 生成 .env.solo（含自签密钥对）
docker compose --env-file .env.solo up -d --build agent-service
```

切换回整栈前先停 Solo 容器（`docker compose --env-file .env.solo stop agent-service`），否则 8000 端口被占用。

### 3.4 容器与宿主机的差异

| 项 | 容器内 | 本地直跑 |
| --- | --- | --- |
| Java profile | `SPRING_PROFILES_ACTIVE` 默认 `prod`，`DEBUG` 固定 `"false"` | 默认 `local`，可注入 `DEBUG` |
| Java 数据库 | `DB_URL` 指向服务名 `postgres:5432` | `localhost:5432` |
| Agent 环境 | `APP_ENV` 默认 `prod`，`DEBUG` 固定 `"false"`，Redis 必需 | `.env` 默认 `dev`，Redis 可选 |
| Agent 数据库 | `STORAGE__POSTGRES_URL` 指向 `pgvector:5432` | `127.0.0.1:5433` |
| Agent 控制面 | `CONTROL_PLANE__BASE_URL=http://application-service:8080` | `http://127.0.0.1:8080` |
| 变量命名 | 根 `.env` 扁平名，由 Compose 映射成 `AUTH__*` / `LLM__*` | 直接写服务原生名 |

Solo 下的 Agent 与整栈的差异（存储、Redis、鉴权、密钥）见 [solo-mode.md](solo-mode.md) §5。

---

## 4. Nginx 路由与超时

模板：`frontend/deploy/nginx/default.conf.template`，由 nginx 官方镜像启动时用 `envsubst` 渲染，只替换 `${BACKEND_UPSTREAM}`、`${AGENT_UPSTREAM}` 与 `${ADMIN_UPSTREAM}`（Compose 注入 `http://application-service:8080`、`http://agent-service:8000`、`http://admin:80`）。

管理端容器使用独立配置 `admin/deploy/nginx/default.conf`：只提供静态文件、`/healthz` 与 SPA 回退，不做反向代理。

| location | 行为 | 超时 / 缓存 |
| --- | --- | --- |
| `= /healthz` | 直接返回 `200 "ok"`，关 `access_log` | — |
| `/assets/` | 静态资源，`try_files $uri =404` | `expires 1y` + `Cache-Control: public, immutable` |
| `= /index.html` | 入口 HTML | `expires -1`（不缓存） |
| `/` | SPA 回退 `try_files $uri $uri/ /index.html` | — |
| `= /admin` | 301 跳到 `/admin/` | — |
| `/admin/` | 转发 `admin:80`，`proxy_pass ${ADMIN_UPSTREAM}/`，**剥掉 `/admin` 前缀** | connect 5s、read 60s、send 60s |
| `/api/` | 转发 Java，`proxy_pass` 不带 URI，**保留 `/api/` 前缀** | connect 5s、read 60s、send 60s |
| `= /agent/api/v1/metrics` | 仅 `allow 127.0.0.1` 与 `10/8`、`172.16/12`、`192.168/16`，其余 `deny all`；关 `access_log`、关缓冲与压缩 | — |
| `/agent/` | 转发 Agent，`proxy_pass ${AGENT_UPSTREAM}/`，**剥掉 `/agent` 前缀** | connect 5s；read / send `3600s`（SSE 长连接）；`proxy_buffering off`、`proxy_cache off`、`gzip off`；透传 `X-Request-ID`；`Connection ""` |

其他全局设置：`client_max_body_size 20m`、`server_tokens off`、gzip 开启、安全响应头 `X-Content-Type-Options` / `X-Frame-Options` / `Referrer-Policy`。

要点：

- `/api/v1/...` 前端请求经 `/api/` 原样到达 Java（后端路由本身就是 `/api/v1/...`）。
- `/admin/users` 到 admin 容器变成 `/users`；管理端静态产物以 `/admin/` 为 base，Router `basepath` 也是 `/admin`，因此深层链接与刷新都正常。
- `/admin/` 与 `/api/` 同源，管理端不需要额外的 CORS 配置，登录时 HttpOnly 刷新 Cookie 可正常往返。
- `/agent/api/v1/chat/stream` 到 Agent 变成 `/api/v1/chat/stream`（`API_PREFIX=/api/v1`）。
- SSE 必须关闭缓冲与压缩，且读超时放到 1 小时；客户端断开后 Agent 会停止图执行。
- 公网只能访问 `WEB_PORT`（默认 80）；Java、Agent、数据库的宿主机端口全部绑定 `127.0.0.1`。

### 4.1 指标端点与统一抓取

三端各自暴露 Prometheus 文本，口径不重复：

| 服务 | 端点 | 说明 |
| --- | --- | --- |
| Agent | `GET /api/v1/metrics` | 13 个指标族（HTTP、SSE、工具、LLM token、outbox、会话删除）；Nginx 白名单 + 可选 `METRICS__TOKEN` |
| Java | `GET /actuator/prometheus` | Micrometer 标准指标（HTTP 请求、JVM、Hikari）；端口只绑回环，Nginx 不代理 `/actuator` |
| LiteLLM | `GET /metrics/` | 上游延迟、错误与 token；必须带 `Authorization: Bearer <LITELLM_MASTER_KEY>`，末尾斜杠不可省 |

统一抓取由 `deploy/prometheus/prometheus.yml` 定义，容器化部署时启动：

```powershell
docker compose --env-file .env --profile infra up -d prometheus
# 界面/接口：http://127.0.0.1:${PROMETHEUS_PORT:-9090}
```

- master key 不写进配置文件：Compose 启动时读取 `LITELLM_MASTER_KEY` 写入容器内 `/tmp/litellm-master-key`，Prometheus 以 `credentials_file` 读取。
- 宿主机直跑 Agent/Java 时，Compose 内的 Prometheus 解析不到服务名，直接 `curl` 对应端点即可，不必为此调整抓取配置。
- 本配置只做指标汇聚；告警规则、SLO 与跨服务 tracing 尚未实现，见 `docs/quality/enterprise-readiness.md` 的 C5–C8。

---

## 5. CI Job 说明

文件：`.github/workflows/ci.yml`。触发：`push` 到 `main` / `develop`、所有 `pull_request`、`workflow_dispatch`；同一分支的旧运行会被取消。

| Job | 名称 | 触发条件 | 内容 |
| --- | --- | --- | --- |
| `changes` | Detect changed paths | 总是执行 | `dorny/paths-filter` 输出 `frontend` / `admin` / `backend` / `agent` / `deploy` / `docs` 布尔值 |
| `frontend` | Frontend (lint / type / test / build) | `frontend/**` 或本 workflow | pnpm 10.18.0 + Node 24；`install --frozen-lockfile`；`lint:ci`；`type-check`；`test:coverage`；装 chromium 后 `e2e:critical`；`check:env --mode production`；`build` |
| `admin` | Admin (lint / type / test / build) | `admin/**` 或本 workflow | pnpm 10.18.0 + Node 24；`install --frozen-lockfile`；`lint:ci`；`type-check`；装 chromium 后 `test`（Vitest browser mode）；`build` |
| `backend` | Backend (Maven verify + JaCoCo) | `application-service/**`、`scripts/check-migrations.ps1` 或本 workflow | JDK 21；`chmod +x mvnw`；`scripts/check-migrations.ps1`；`./mvnw -B -ntp verify`；上传 `jacoco-report` |
| `agent` | Agent (ruff / mypy / pytest / evals) | `agent-service/**` 或本 workflow | Python 3.12 + uv；真实 `pgvector/pgvector:pg18` 与 `redis:8-alpine` Service；`uv sync --frozen`；`ruff check app tests evals run.py`；`mypy`；`pytest -q --cov=app`；`python -m evals --fake` |
| `docs` | Docs (link / env keys) | `docs/**`、根与四份服务 `README.md`、`.trae/rules/**`、`scripts/**` 或本 workflow | `scripts/check-doc-links.ps1`、`scripts/check-env-docs.ps1` |
| `docker` | Docker build (matrix) | 四端任一变化 | Buildx 矩阵构建 `frontend` / `admin` / `application-service` / `agent-service` 四个镜像，`push: false` |
| `compose` | Validate docker-compose | `docker-compose.yml`、`deploy/**` 或本 workflow | 注入 CI 占位变量后 `docker compose -f docker-compose.yml config -q` |

注意：

- 每条 Job 都是路径分流，改 Java 不会触发前端 Job，因此「Required Check 不出现」是预期行为；分支保护里只勾选实际会跑的检查，或把 `changes` 也纳入。
- `docs` Job 的两个脚本是文档门禁：链接失效或文档里出现未登记的配置键都会失败。
- `compose` Job 只校验根 `docker-compose.yml`，不校验 `deploy/docker-compose.infra.yml`。
- 管理端镜像由 `docker` Job 的 `admin` 矩阵项构建；`VITE_BASE_PATH=/admin/` 作为构建参数传入。
- CI 不需要业务密钥；所有值都是 `ci-only-*` 或测试占位（`JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` 仅用于通过变量插值校验，不连接任何服务）。

---

## 6. 发布与回滚

### 6.1 镜像与标签

当前 Compose 使用固定本地标签：`agent/frontend:local`、`agent/admin:local`、`agent/application-service:local`、`agent/agent-service:local`（`docker-compose.yml`）。仓库尚未推送到任何镜像仓库。

**建议（非现状）**：生产给镜像打 Git SHA 或语义化标签，把 Compose 的 `image:` 改为带标签的版本，回滚时改回旧标签，不必重新构建。

### 6.2 更新发布

```bash
git pull --ff-only
docker compose --profile full up -d --build application-service frontend   # 只重建改动过的服务
docker compose --profile full ps
```

只更新管理端：

```bash
docker compose --profile full up -d --build admin
docker compose restart frontend                                # 刷新 admin 上游解析（BUG-04）
```

只更新 Agent：

```bash
docker compose --profile full up -d --build agent-service
```

判定是否需要重建：

| 改动类型 | 是否需要 `--build` |
| --- | --- |
| 运行时环境变量（数据库、JWT、LLM、Redis、模型运行时） | 否，重启容器即可 |
| `VITE_*` 构建参数 | **是**，前端与管理端镜像必须重建（变量已写进静态产物） |
| 任一端源码或 Dockerfile | **是**，对应服务必须重建 |
| Nginx 模板 `frontend/deploy/nginx/default.conf.template` | **是**，前端镜像必须重建 |
| 管理端 Nginx 配置 `admin/deploy/nginx/default.conf` | **是**，管理端镜像必须重建 |

**重建后端或管理端后必须重启前端（BUG-04）**：Nginx 在启动时解析 `proxy_pass` 的主机名并缓存到 worker 生命周期内，容器重建后 IP 变化不会自动刷新。只重建 `application-service`、`agent-service` 或 `admin` 时，必须补一步：

```bash
docker compose restart frontend
```

否则 `/api/`、`/agent/` 与 `/admin/` 会持续返回 502，直到前端容器重启。模板顶部也写有同样的警示（`frontend/deploy/nginx/default.conf.template`）。

> 为何不用 `resolver` 变量解析上游：Agent 侧依赖 `proxy_pass ${AGENT_UPSTREAM}/` 的末尾斜杠剥掉 `/agent` 前缀，改成变量形式后 URI 处理语义会变，风险高于重启一步；因此选择流程固化。

### 6.3 数据库变更

- Java 结构变更只走 Flyway（`application-service/src/main/resources/db/migration`，启动时由 `spring.flyway` 执行）。
- 已合入主干的版本脚本**只可追加，不可修改**；结构变更遵循「先扩展、后收缩」。
- 数据库变更必须向前兼容：回滚到上一版本镜像后旧代码仍能连上当前库并正常启动。
- Agent 会话库在 `STORAGE__AUTO_SETUP=true` 时由应用启动幂等建表；托管库无 DDL 权限时设为 `false`，把同一条 DDL 纳入上线步骤。
- `scripts/check-migrations.ps1` 在 CI 中强制：命名 `V<number>__<snake_case>.sql`、版本唯一且连续、全部纳入版本控制。

### 6.4 回滚

```bash
# 方式 A：回到上一个稳定提交并重建（当前 :local 标签下的唯一手段）
git log --oneline -5
git checkout <上一个稳定提交>
docker compose --profile full up -d --build

# 方式 B（建议）：保留上一版本镜像与 .env，只切换镜像标签
# 1) 发布前把当前镜像另存为 <上一版本>
# 2) 把 docker-compose.yml 的 image 改回旧标签，执行 docker compose up -d
```

回滚必须同时保留**上一版本的 `.env` 与 Compose 文件**；只回滚镜像而沿用新配置，会因变量缺失/校验失败而起不来。

### 6.5 备份与恢复

```bash
# 业务库
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backup-business.sql

# Agent 会话库
docker compose exec -T pgvector sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backup-agent.sql

# 恢复（以业务库为例）
cat backup-business.sql | docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

账号与库名取自容器内环境变量（`POSTGRES_USER` / `POSTGRES_DB`），不在脚本里写死；`pgvector` 容器内同样是 `POSTGRES_*` 三个变量，值来自 `AGENT_POSTGRES_*`。BYOK 主密钥 `MODEL_CRED_MASTER_KEY` 必须与数据库备份**分开保管**——丢失即全部已存凭证不可用。

---

## 7. 校验命令

```powershell
# Compose 变量插值与语法（缺变量在此步报错）
docker compose --env-file .env config -q

# 文档相对链接
powershell -NoProfile -File scripts/check-doc-links.ps1

# 文档中的环境变量键必须在某个 .env.example 中有登记
powershell -NoProfile -File scripts/check-env-docs.ps1

# Flyway 迁移命名 / 版本连续 / 已纳入版本控制
powershell -NoProfile -File scripts/check-migrations.ps1

# 模型用量对账（只读；需 postgres 容器在运行，默认核对前一 UTC 自然日）
powershell -NoProfile -File scripts/reconcile-model-usage.ps1
```

服务级门禁（详细参数见各服务文档）：

```powershell
corepack pnpm --dir frontend lint:ci
corepack pnpm --dir frontend type-check
corepack pnpm --dir frontend test:coverage
corepack pnpm --dir frontend e2e:critical

cd application-service; .\mvnw.cmd -q verify

uv --directory agent-service run ruff check app tests evals run.py
uv --directory agent-service run mypy
uv --directory agent-service run pytest -q --cov=app --cov-report=term-missing
uv --directory agent-service run python -m evals --fake
```

部署后冒烟验证（在服务器或本机容器网络内执行）：

```bash
curl -fsS http://localhost/healthz                                  # 前端 ok
curl -fsS http://localhost/admin/healthz                             # 管理端 ok（经 /admin/ 代理）
curl -fsS http://127.0.0.1:8080/actuator/health                     # {"status":"UP"}
curl -fsS http://127.0.0.1:8000/api/v1/health/live                   # 进程存活
curl -fsS http://127.0.0.1:8000/api/v1/health/ready                  # 依赖就绪，redis=up
curl -s  http://localhost/api/v1/auth/me                             # 未登录应返回 401（说明 /api/ 已透传到 Java）
```

健康端点语义：`/health/live` 只看进程；`/health/ready` 会真实探测 checkpointer 与 Redis，未就绪返回 503（编排系统应摘流量而非重启）。

---

## 8. 常见故障排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `docker compose up` 报 `POSTGRES_PASSWORD is required` | 没有 `.env`，或变量未填 | `cp .env.example .env` 后替换所有 `replace-with-*`；确认 `--env-file` 路径 |
| 前端容器日志 `host not found in upstream "application-service"` | Nginx 启动时要解析上游域名，容器不在同一 Compose 网络 | 用 Compose 启动；不要单独 `docker run` 前端镜像而不加网络 |
| `/api/` 返回 502 | Java 未通过健康检查（数据库未就绪、密钥非法、配置守卫拒绝） | `docker compose logs application-service`；对照 §8 下方「Java 启动失败」 |
| `/admin/` 返回 502 | admin 容器未启动，或前端启动时 admin 主机名未解析 | `docker compose ps admin`；`docker compose logs admin`；必要时 `docker compose restart frontend` |
| `/admin/` 页面空白、资源 404 | 构建 base 与 Nginx 前缀不一致 | 确认 Compose 的 `VITE_BASE_PATH=/admin/`，并检查浏览器请求是否发往 `/admin/assets/...` |
| 前端构建报 `[check-env] 缺少必填变量 VITE_API_BASE_URL` | `docker build` 未传 build args | 检查 `docker-compose.yml` 的 `frontend.build.args`；本地执行前先设置环境变量 |
| Java 启动报 `生产环境配置校验失败（prod）` | 命中 `ProdConfigGuard` | 逐项修：`debug` 必须 false；`JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` 必须成对且为合法 PEM（不能是 `change-me` / `replace-with-*`）；`AUTH_COOKIE_SECURE=true`；`DB_PASSWORD` 不能为空或 `postgres`；开启运行时后 `INTERNAL_AUTH_CLIENT_SECRET` ≥ 16 字符 |
| Java 启动报 `password authentication failed for user "agent"`，并伴随 Flyway / MyBatis Bean 注入失败 | 启动时注入的 `DB_PASSWORD` 与数据库实际口令不一致；`POSTGRES_PASSWORD` 只在数据卷首次初始化时生效，改 `.env` 不会改已有角色口令 | 用 `scripts/dev/start-local.ps1` 启动（自带真实网络路径预检）；确需换口令时先 `ALTER ROLE` 再同步根 `.env`；不要使用 `.env.example` 的 `change-me` |
| `docker exec ... psql` 能连，但应用连接报口令错误 | 容器内 `127.0.0.1` 命中 `pg_hba.conf` 的 `trust` 规则，未校验密码 | 从容器网络或宿主机验证口令（脚本预检即用 `pgvector → postgres` 的 `scram-sha-256` 路径） |
| Agent 启动报 `AUTH__JWT_PUBLIC_KEY 不是合法的 PEM 公钥` | 单行 PEM 的 `\n` 未还原，或公钥与 Java 不是同一对 | 按 `environment-variables.md` §5.1 重新生成并成对注入 |
| 登录成功但刷新页面退回登录页 | 刷新 Cookie 未被保存或携带 | 确认 `AUTH_COOKIE_SECURE` 与访问协议匹配（https 用 `true`，本地 http 用 `false` 且 profile 非 prod）；Cookie `Path` 未被代理改写；`CORS_ALLOWED_ORIGINS` 含实际访问域名 |
| Agent 健康但对话一律 503 | `LLM__API_KEY` 未配置或仍是占位值（dev 下不阻止启动） | 配置真实密钥；生产建议 `APP_ENV=prod` 让占位值直接拒绝启动 |
| 指标端点 403 | Nginx `allow`/`deny` 命中，或 `METRICS__TOKEN` 与请求头不匹配 | 从容器网络或私网抓取；核对 `X-Metrics-Token` |
| CI 前端 Job 报 `ERR_PNPM_OUTDATED_LOCKFILE` | `package.json` 与 `pnpm-lock.yaml` 不一致 | 本地 `corepack pnpm install` 后提交锁文件 |
| `changes` 通过但前端 Job 被跳过 | 本次改动不在 `frontend/**` | 预期行为，见 §5 |
| CI `docs` Job 失败 | 相对链接失效，或文档里出现 `.env.example` 未登记的键 | 运行两个 `scripts/*.ps1` 定位；补登键属配置变更，需单独提交 |

**待确认**：`application-service/README.md` 曾提到「按生产配置指南的 SSH 隧道方式连接云上数据库」，但仓库中从未存在该章节；本指南不提供 SSH 隧道步骤，数据库也不应为了联调暴露到公网。具体隧道方案需项目负责人确认后补充。
