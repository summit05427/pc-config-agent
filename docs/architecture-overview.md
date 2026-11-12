# 总体架构

| 项 | 内容 |
| --- | --- |
| 状态 | Current |
| 最后核验 | 2026-11-01 |
| 权威性 | Authoritative（系统架构、服务边界、数据归属、通信链路） |
| 主要证据 | `frontend/package.json`、`application-service/pom.xml`、`agent-service/pyproject.toml`、`admin/package.json`、`frontend/deploy/nginx/default.conf.template`、`admin/deploy/nginx/default.conf`、根 `docker-compose.yml` |

适用范围：`frontend/`、`admin/`、`application-service/`、`agent-service/` 及其部署编排。本文只描述当前代码可证明的结构与已确认决策；功能级细节见各服务文档。

> 2026-11-01 修订：修正前端证据路径；补记 Agent → Java 的内部调用（服务令牌 + `X-User-Token`）；把已实现的登录失败限流从「未实现」移出；记录管理端经 Nginx `/admin/` 与 Compose 接入。

## 1. 各端职责

| 端 | 目录 | 技术栈（已验证） | 负责 | 明确不负责 |
| --- | --- | --- | --- | --- |
| 前端 | `frontend/` | React 19 + TypeScript + Vite + TanStack Router/Query + Zustand + Tailwind/Radix；容器内 Nginx 同时承担静态托管与反向代理 | 界面、路由、状态、SSE 消费、登录态维护 | 不保存模型密钥、不签发 Token、不做真实权限校验 |
| Java 业务端 | `application-service/` | Java 21 + Spring Boot 4.1.1 + Spring Modulith 2.1.2 + MyBatis + Flyway + Spring Security（OAuth2 Resource Server, RS256） | 用户认证、双令牌签发与刷新会话、业务数据与权限、模型运行时控制面（模型目录 / BYOK 凭证 / 额度 / 用量） | 不调用 Agent、不执行对话编排、不下发模型密钥明文 |
| Python Agent 端 | `agent-service/` | Python 3.12 + FastAPI + LangGraph + LangChain OpenAI + sse-starlette | 对话编排、工具调用、会话持久化、SSE 推流；PC 配置走确定性八节点流水线（需求解析 → 校验 → HITL 澄清门控 → 候选检索 → Java 求解 → 兼容性复核 → HITL 兼容性门控 → 解释渲染） | 不建用户表、不签发生产 Token、不查 Java 业务库、不自行计算价格与兼容性 |
| 管理端 | `admin/` | React 19 + TypeScript + Vite + TanStack Router/Query + Zustand + Tailwind/shadcn-admin | 管理员登录、用户管理（状态 / 角色）、审计日志查询 | 不调用 Agent、不连接数据库、不持有模型密钥、不实现用户端功能 |

证据：`frontend/package.json`、`application-service/pom.xml`、`agent-service/pyproject.toml`、`admin/package.json`、`frontend/deploy/nginx/default.conf.template`。

管理端与用户端同源部署：浏览器访问 `/admin/`，由 frontend Nginx 剥离前缀后转发到 `admin` 静态容器；接口仍走同源 `/api/`。结构与认证细节见 [services/admin/architecture.md](services/admin/architecture.md)，部署见 [deployment/deployment-guide.md](deployment/deployment-guide.md)。

## 2. 部署拓扑与路径映射

```text
浏览器
  └─ Nginx（frontend 容器，:80，唯一公网入口）
       ├─ /            → 前端静态资源（TanStack Router history 回退 index.html）
       ├─ /admin/      → admin:80 管理端静态站点（去掉 /admin 前缀，history 回退）
       ├─ /api/        → application-service:8080   保留 /api 前缀
       └─ /agent/      → agent-service:8000         去掉 /agent 前缀
```

已验证事实（`frontend/deploy/nginx/default.conf.template`）：

- `/api/` 使用 `proxy_pass ${BACKEND_UPSTREAM}`（不带 URI），因此 `/api/v1/auth/login` 原样转发到 Java。
- `/agent/` 使用 `proxy_pass ${AGENT_UPSTREAM}/`（带 `/`），因此 `/agent/api/v1/chat/stream` 转发为 Agent 的 `/api/v1/chat/stream`。
- `/agent/` 单独放宽为 `proxy_read_timeout 3600s`、`proxy_send_timeout 3600s`，并关闭 `proxy_buffering`、`proxy_cache`、`gzip`；`/api/` 为 60s，不做长连接优化。这直接对应「Java 接口是短请求、Agent 对话是长流」的用法差异。
- `/agent/` 显式清空 `Connection` 头，避免上游把 SSE 误判为 WebSocket 升级。
- `/admin/` 使用 `proxy_pass ${ADMIN_UPSTREAM}/`（带 `/`），把 `/admin/users` 转发为 admin 容器的 `/users`；管理端构建 base 为 `/admin/`，Router `basepath` 同值，因此资源与深层链接都能正确命中。
- 指标端点 `/agent/api/v1/metrics` 使用独立的精确 location：仅 `allow` 回环与私网网段，其余 `deny all`，并关闭 `access_log` 与压缩；应用内再用可选 `METRICS__TOKEN` 兜底（2026-10-28 决策：网关白名单为主、应用内鉴权兜底）。

端口与编排（`docker-compose.yml`、`deploy/docker-compose.infra.yml`）：Java 暴露 `127.0.0.1:8080`，Agent 暴露 `127.0.0.1:8000`，均只绑定回环地址；基础设施为 `postgres:5432`（Java 库 `agent`）、`pgvector:5432`（Agent 库 `agent_service`，宿主映射 5433）、`redis:6379`（Agent 可选依赖）。

## 3. 实际调用关系

```text
浏览器 ──Bearer JWT──> Nginx ──> Java  /api/v1/auth/**、/api/v1/users/me/**、/api/v1/models、/api/v1/model-connections、/api/v1/users/me/model-usage、/api/v2/**
                               （refresh / logout 额外携带 HttpOnly Cookie `agent_refresh`）
浏览器 ──Bearer JWT──> Nginx ──> Agent /api/v1/chat/stream
                               Agent /api/v1/sessions/**、/api/v1/auth/dev-token、/api/v1/health/*

Agent ──服务令牌 + X-User-Token──> Java(内网直连) /internal/v1/auth/service-token
                                              /internal/v1/model-tasks**
                                              /internal/v1/model-tasks/{taskId}/credential-lease
                                              /internal/v1/model-access/check
                                              /internal/v1/model-usage
                                              /internal/v1/pc/hardware/**
                                              /internal/v1/pc/benchmarks
                                              /internal/v1/pc/offers
                                              /internal/v1/pc/builds/**
```

- **已验证事实**：前端有两套请求门面。Java 请求走 `frontend/src/core/http/httpJson.ts`（axios + 信封拆解 + 401 单飞刷新）；Agent 请求走 `frontend/src/core/http/sseStream.ts`（`fetch` + ReadableStream，读裸 JSON 与 SSE）。业务域 API 在 `frontend/src/features/<domain>/api/`，组件与 feature 不直接使用 `axios` / `fetch`。
- **已验证事实**：前端对 Java 的调用集中在 `features/auth/api/auth.ts`（`/auth/login|refresh|logout|logout-all|me`）、`features/sessions/api/user.ts`（`/users/me/profile|password|sessions`）、`features/models/api/models.ts`、`features/usage/api/`、`features/settings/api/`。
- **已验证事实**：前端对 Agent 的调用集中在 `frontend/src/features/sessions/api/{sessions,stream-chat}.ts`（`/sessions`、`/sessions/{thread_id}`、`/sessions/{thread_id}/messages`、`/sessions/{thread_id}/model`、`/chat/stream`）。
- **已验证事实（2026-11-01）**：管理端 `admin/` 是独立调用方，只访问 Java 的 `/api/v1/auth/**` 与 `/api/v1/admin/**`（用户列表、状态与角色变更、审计日志），所有请求经 `admin/src/core/http/client.ts`；不调用 Agent，也不与用户端共享认证 store。
- **已确认决策（2026-10-28）**：保持「前端经 Nginx 直连 Agent」的策略，Java 不新增 Agent 客户端、不代理 SSE 流。
- **已验证事实**：`application-service` 中不存在任何 `WebClient` / `RestTemplate` / `RestClient` / Feign 客户端，也没有 Agent 地址配置项（全仓检索仅命中 `mvnw.cmd` 中的 `System.Net.WebClient`）。前端仍是 Agent 的**唯一入站调用方**。
- **已验证事实（2026-11-01 补记）**：反方向存在服务间调用——Agent 经 `agent-service/app/services/control_plane.py` 调用 Java 的 `/internal/v1/**`，携带服务令牌（`token_use=service`），用户维度接口额外带 `X-User-Token`。该调用只走内网、不经 Nginx，契约见 [api-contract.md](api-contract.md) §5.6。

## 4. 信任边界与身份传递

- **已确认决策**：Java 是生产 Token 的唯一签发方；Agent 只校验，不建用户表、不签发生产 Token。
- **双令牌模型**：Access Token 是 RS256 JWT，只存前端内存，有效期由 `JWT_ACCESS_TTL` 控制（默认 `10m`）；Refresh Token 是 32 字节不透明随机串，只经 `HttpOnly` Cookie `agent_refresh` 下发，JS 不可读，闲置 7 天 / 绝对 30 天（`AUTH_REFRESH_IDLE_TTL` / `AUTH_REFRESH_ABSOLUTE_TTL`）。
- JWT 参数（已验证）：算法固定 RS256，issuer 固定 `agent-application-service`，JWS Header 带 `kid`（`JWT_KID`），claims 为 `sub` / `iss` / `iat` / `exp` / `aud` / `jti` / `roles` / `token_use="access"` / `sid`；`sub` 是 `users.public_id`（UUID），内部自增主键与登录名都不进令牌；`roles` 不带 `ROLE_` 前缀。`sid` 取签发时所在 `refresh_sessions.family_id`，只用于识别「当前设备会话」（改密保留当前族、设备列表标记 `current`），不参与鉴权，Agent 验签忽略该字段。
- Java 用私钥（`JWT_PRIVATE_KEY`）签发、用公钥（`JWT_PUBLIC_KEY`）自校验；Agent 只持 `AUTH__JWT_PUBLIC_KEY`，按 `kid` 从本进程公钥白名单选钥（未知 `kid` 直接拒绝），算法只允许 RS256，并强制校验 `exp` / `sub` / `iss` / `aud` / `token_use="access"`；`aud` 不是可选项。
- 刷新会话（`refresh_sessions` 表）：库内只存令牌的 SHA-256 摘要，每次刷新都轮换并作废旧令牌；同一 `family_id` 构成一条令牌族，超宽限期重放旧令牌会整族撤销（`revoked_reason=replay`）。
- 归属隔离有两层：Agent 用令牌 `sub`（公开 UUID）拼成 `user_id:thread_id` 作为图状态键；历史消息查询在 SQL 条件中带 `user_id`。两层都不依赖客户端的任何声明。
- 浏览器只持短生命周期 Access Token（内存）与不可读的刷新 Cookie。Agent → Java 的内部调用不复用用户令牌：改用长期服务令牌（`token_use=service`，`sub=agent-service`，只带 scope、只能访问 `/internal/v1/**`），需要用户维度的接口再额外携带 `X-User-Token`（见 [api-contract.md](api-contract.md) §5.6）。
- 数据边界：Java 与 Agent 使用不同数据库实例与库名，互不查询对方业务表；Agent 不读 `agent` 库，Java 不读 `agent_service` 库。

## 5. 关键数据流

**登录**：浏览器 `POST /api/v1/auth/login` → Java 校验账号口令 → 签发 Access Token 并通过 `Set-Cookie` 下发 Refresh Token（信封内 `data` 为 `{accessToken, tokenType, expiresIn, user}`，不含刷新令牌）→ 前端把 Access Token 写入内存，刷新页面后由守卫调用 `/auth/refresh` + `/auth/me` 恢复登录态。

**刷新**：前端遇到 401（或页面启动时无 Access Token）先做单飞刷新，并发请求共用一次 `POST /api/v1/auth/refresh`；Java 校验 Cookie 来源、轮换刷新令牌并换发新的 Access Token；刷新失败才清理登录态并跳转登录页。`/auth/logout` 撤销当前刷新会话并清除 Cookie，失败不影响本地清理。

**对话**：浏览器 `POST /agent/api/v1/chat/stream` → Nginx 剥前缀 → Agent 校验 JWT、按 `user_id:thread_id` 取锁 → LangGraph 流式执行 → SSE 逐帧下发 `token` / `reasoning` / `tool_call` / `tool_result` → 本轮结束后先把完整消息写入 `session_messages`、会话元数据 upsert 到 `session_meta`，再发 `done`。

**历史**：浏览器 `GET /agent/api/v1/sessions` 读取 Postgres `session_meta`（含标题，按最近活跃倒序）；`GET /agent/api/v1/sessions/{thread_id}/messages` 按 `user_id` 与 `thread_id` 在数据库中分页查询 `session_messages`（支持 `order=asc|desc`）；没有任何消息时返回 404 `session_not_found`。列表与历史都不依赖 Redis，`PATCH` / `DELETE /sessions/{thread_id}` 分别用于重命名与删除会话（删除时尽力清理 checkpointer）。

## 6. 已确认决策：统一入口与职责划分（C-08）

原始决策（项目负责人确认）：

> 保留 Nginx 作为统一公网入口，Java 与 Agent 使用不同的路由。Agent 不直接暴露公网端口，内部端口仅允许受信任的网络路径访问；Java 负责业务身份与授权，Agent 验证调用凭证。

落地状态：

| 决策点 | 落地情况 |
| --- | --- |
| Nginx 统一入口、`/api/`、`/agent/` 与 `/admin/` 分流 | 已实现，见第 2 节 |
| Agent 不暴露公网端口 | 编排中仅绑定 `127.0.0.1:8000`；容器网络内可被 Nginx 访问 |
| Java 负责身份与授权 | 已实现登录与 Token 签发；授权规则目前只有 `/api/v1/admin/**` 需 `ADMIN` 角色 |
| Agent 验证调用凭证 | 已实现，见第 4 节 |
| 前端直连 Agent（不经 Java 代理） | **已确认决策（2026-10-28）**：保持现状，Java 不新增 Agent 客户端 |

决策与实现已对齐：C-08 只要求「Java 负责身份、Agent 校验凭证、Nginx 统一入口」，不要求 Java 代理 Agent 调用；2026-10-28 进一步确认保持前端直连 Agent，因此无待决差异。

## 7. 未实现能力清单

以下内容曾被列为未实现或存在边界，按当前代码状态逐项标注；标为未实现的条目不得作为契约引用：

- Java 调用 Agent 的服务间客户端、服务间鉴权与重试策略：**已确认不做**（2026-10-28），由前端经 Nginx 直连 Agent。
- 刷新令牌与令牌吊销列表：**已实现**（见第 4 节），不再属于未实现能力；仅「Access Token 黑名单 / 按用户强制下线全员」仍未实现。
- Agent 侧的 RAG 与长期记忆：**机制已实现**（RAG 与历史摘要默认关闭；RAG 不内置知识库，检索器与记忆实现由接入方提供），不再属于未实现能力。
- Agent 侧的人工审批、多 Agent 编排。
- 接口限流：**登录失败限流已实现**（`InMemoryLoginAttemptLimiter`，进程内单实例，超限 429 `10007`，仅统计认证失败、成功登录清零）；**其余接口未实现限流**。模型请求额度（`40201`）属于模型运行时配额，不是通用限流。
- 前端对 Agent 的跨域直连：当前走同源 `/agent/`，`CORS_ALLOWED_ORIGINS` 与 Agent `cors_origins` 只在分域部署时才需要。
- PC 配置：**已实现**。Java 提供候选、跑分、报价、求解、兼容性校验与快照七类内部接口；Agent 以确定性单图替换原 ReAct 图，LLM 只做需求解析与解释生成。2026-11-12 实测目录 402 款、报价 402 条（全部 `PLATFORM_OBSERVED`，`data_status=PLATFORM_OBSERVED_ONLY`）、跑分 169 条；机箱限高/冷排与主板最大内存字段仍待补齐，见 [planning/roadmap.md](planning/roadmap.md) §8。

## 8. 已知不一致与待确认

| 编号 | 内容 | 状态 |
| --- | --- | --- |
| P-01 | ~~决策要求 Java 调用 Agent~~ → **已关闭（2026-10-28）**：确认保持前端直连 Agent，Java 不新增客户端 | 已确认决策 |
| P-02 | Java `roles` 大写（`ADMIN`），Agent 开发令牌固定 `["user"]`，工具角色校验见 `agent-service/app/agent/registry.py` | 已验证事实，非缺陷；跨端角色命名需保持一致 |
| P-03 | ~~Agent `GET /sessions/{thread_id}/messages` 默认 `size=20`，前端固定请求 `size=50`~~ → **已关闭（2026-10-28）**：三端默认统一 20，前端显式请求历史 100、会话 20（`HISTORY_PAGE_SIZE` / `SESSIONS_PAGE_SIZE`） | 已统一 |
| P-04 | ~~`/api/v1/metrics` 无鉴权~~ → **已关闭（2026-10-28）**：Nginx 白名单为主，`METRICS__TOKEN` 兜底 | 已确认决策 |
