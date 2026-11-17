# 系统架构总览

| 项 | 内容 |
| --- | --- |
| 适用范围 | 四端职责、部署拓扑、调用关系、信任边界与未实现能力 |
| 状态 | Current |
| 最后更新 | 2026-11-17 |
| 权威性 | Authoritative（系统级架构事实源）；接口字段见 [api-contract.md](./api-contract.md) |
| 主要证据 | 各端 `src/main`、根 `docker-compose.yml`、`deploy/nginx/`、`agent-service/app/` |

## 1. 结论先行

- 只有 Frontend Nginx 暴露公网；Admin 由同一 Nginx 以 `/admin/` 托管。
- 浏览器只调用同源 `/api/*`（Java）与 `/agent/api/*`（Agent），不跨域。
- Java 是 Token 唯一签发方，也是型号、规格、价格、兼容性与预算的事实权威。
- Agent 负责对话编排与 LLM 选型；不访问 Java 数据库，不签发生产 Token。
- 开发阶段四端在宿主机运行，容器只跑 `postgres`、`pgvector`、`redis`。

## 2. 技术栈

| 端 | 技术 | 职责 |
| --- | --- | --- |
| `frontend/` | React 19 + TS + Vite + TanStack Router/Query + Zustand | 会话、SSE、生成式 UI、PC 配置展示 |
| `admin/` | React 19 + TS + Vite + TanStack Router/Query（shadcn-admin） | 管理员登录、用户、审计日志、模型目录与定价 |
| `application-service/` | Java 21 + Spring Boot + Flyway + PostgreSQL | 用户、权限、JWT、模型目录、PC 配置事实接口 |
| `agent-service/` | Python 3.12 + FastAPI + LangGraph | 会话图、工具治理、检索接缝、SSE 输出 |
| `deploy/` | Nginx、Compose、备份/恢复脚本 | 公网入口与中间件编排 |

## 3. 部署拓扑

```text
公网 :80
  └─ frontend Nginx
       ├─ /            → frontend 静态资源
       ├─ /admin/      → admin 静态资源
       ├─ /api/        → application-service:8080
       └─ /agent/api/  → agent-service:8000

Compose 内网
  ├─ postgres:5432     （agent 库由 app 管理；agent_service 库由 LangGraph 管理与业务表）
  ├─ pgvector:5433     （RAG 预留，未启用）
  └─ redis:6379        （分布式锁；缓存接缝）
```

- Nginx 在入口剥掉 `/agent` 前缀，Agent 实际收到 `/api/*`；Java 保留 `/api/*`。
- Agent 调用 Java 走 `AGENT__JAVA_BASE_URL` 内网地址，不经 Nginx。
- 容器内互访使用 Compose 服务名，禁止硬编码公网地址。

## 4. 调用关系

### 4.1 浏览器 → 四端

| 路径 | 目标 | 说明 |
| --- | --- | --- |
| `/api/v1/auth/**` | Java | 注册、登录、刷新、登出、当前用户 |
| `/api/v1/admin/**` | Java | 管理端接口，需管理员角色 |
| `/api/v1/models/**`、`/api/v1/model-runtime/**` | Java | 模型目录、默认模型、BYOK |
| `/agent/api/v1/chat/stream` | Agent | SSE 对话；`resume` 恢复 HITL，与 `regenerate` 互斥 |
| `/agent/api/v1/sessions/**` | Agent | 会话列表、历史、重命名、删除 |
| `/agent/api/v1/health/**` | Agent | 健康检查与就绪状态 |

### 4.2 Agent → Java 内部接口

| 接口 | 用途 | 令牌 |
| --- | --- | --- |
| `/internal/v1/auth/exchange` | 用户令牌 → 内部会话 | 服务令牌 |
| `/internal/v1/models/resolve` | 解析模型配置 | 服务令牌 |
| `/internal/v1/pc/hardware/**` | 候选、详情 | 服务令牌 |
| `/internal/v1/pc/benchmarks` | 跑分 | 服务令牌 |
| `/internal/v1/pc/offers` | 报价 | 服务令牌 |
| `/internal/v1/pc/builds/validate` | 完整兼容校验 | 服务令牌 |
| `/internal/v1/pc/builds/validate-partial` | 部分兼容校验 | 服务令牌 |
| `/internal/v1/pc/builds/compose` | 组装、预算、快照 | 服务令牌 + `X-User-Token` |
| `/internal/v1/pc/builds/{buildId}` | 快照回读 | 服务令牌 + `X-User-Token` |

- 服务令牌 `token_use=service`；用户维度接口额外带 `X-User-Token`。
- 方向固定：Agent → Java。Java 不得调用 Agent。
- 内部接口不经 Nginx，不对外暴露。

### 4.3 四端共同依赖

- PostgreSQL：Java 使用 `agent` 库；Agent 使用 `agent_service` 库；互不查询对方业务表。
- Redis：Agent 用分布式锁防同一 `thread_id` 并发写；可替换的缓存/限流接缝。
- 模型网关：固定 OpenAI 兼容接口，模型密钥不进前端、不进日志。

## 5. 端内结构

### 5.1 Frontend

- `src/app` 路由与 Provider；`src/features/*` 按业务域分包。
- `src/shared` 提供 HTTP 门面、SSE 客户端、UI 组件与工具。
- Access Token 只存内存；刷新依赖 Java 下发的 `HttpOnly` Cookie。
- SSE 事件：`token`、`reasoning`、`tool_call`、`tool_result`、`citations`、`interrupt`、`done`、`error`。

### 5.2 Admin

- 仅调用 Java `/api/v1/admin/**` 与 `/api/v1/auth/**`。
- 不调用 Agent、不查询数据库、不保存模型密钥。
- 认证由 Java 负责；前端路由守卫只做交互控制。

### 5.3 Application Service

- `auth`、`user`、`admin`、`audit`、`model`、`runtime`、`pcbuild` 分包。
- `pcbuild` 分 `domain` / `application` / `infrastructure` / `web`，兼容规则集中在 domain。
- Flyway 管理 Schema；V24 创建 `pc_build_snapshots`。
- 统一错误码与响应封装，内部接口与公网接口共用异常体系。

### 5.4 Agent Service

- `app/api` 只做协议层；`app/services/turn.py` 负责一轮对话生命周期。
- `app/agent/pc/` 装配 9 节点图；工具经 `app/agent/tool_governance` 统一治理。
- `app/services/pc_client.py` 是 Java PC 接口唯一客户端。
- 会话业务表与 LangGraph checkpointer 分离；`STORAGE__BACKEND=postgres` 时启用持久化。

## 6. 信任边界

| 边界 | 规则 |
| --- | --- |
| 浏览器 ↔ Java | JWT 校验 + 用户归属；管理端额外校验管理员角色 |
| 浏览器 ↔ Agent | 仅聊天与历史接口；错误统一 `{code,message,requestId}` |
| Agent ↔ Java | `/internal/v1/**` 只认 `token_use=service`；用户维度校验 `X-User-Token` 的 `sub` |
| Java ↔ DB | 参数化 SQL；资源按 `user_id` 过滤 |
| 模型网关 | API Key 只来自环境变量或加密存储；日志脱敏 |
| 日志 | 不记录密码、Token、API Key、完整对话、手机号与身份证号 |

## 7. PC 配置现状

- 选型由 Agent LLM 在 `build_architect` 完成；Java 只提供候选、跑分、报价、组装、9 条兼容校验与快照。
- Java 不提供求解/选型端点；旧求解器节点与搜索实现已删除。
- 运行时目录 402 款；报价 402 条全部 `PLATFORM_OBSERVED`，无 `OWNER_VERIFIED`。
- 默认模型 `deepseek:deepseek-flash`。
- 9 节点图、工具与 HITL 详见 [agent-workflows.md](./services/agent-service/agent-workflows.md)。
- 兼容规则详见 [compatibility-rules.md](./pc-config/compatibility-rules.md)。

## 8. 未实现能力

- 多 Agent 协作【规划中】。
- RAG 知识库与向量检索【规划中】；`pgvector` 仅预留。
- 管理端硬件/报价维护页【未实现】。
- 自动报价采集、价格历史、过期清理【未实现】。
- 多方案对比、交互式换件【未实现】。
- 离线治理主数据接入运行时【未实现】。

## 9. 相关文档

- 契约：[api-contract.md](./api-contract.md)
- 前端：[services/frontend/architecture.md](./services/frontend/architecture.md)
- Java：[services/application-service/architecture.md](./services/application-service/architecture.md)
- Agent：[services/agent-service/architecture.md](./services/agent-service/architecture.md)
- 管理端：[services/admin/architecture.md](./services/admin/architecture.md)
- PC 模块：[pc-config/README.md](./pc-config/README.md)
- 决策：[ADR 0027](./adr/0027-pc-config-decisions.md)、[ADR 0028](./adr/0028-llm-led-build-selection.md)
