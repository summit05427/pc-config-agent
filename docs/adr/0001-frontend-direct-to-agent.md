# ADR-0001：前端经 Nginx 直连 Agent，Java 不代理 SSE

- 状态：Accepted（2026-10-28）
- 影响范围：前端请求层、Nginx 路由、Java 与 Agent 的职责边界、鉴权
- 证据：`docs/architecture-overview.md` §3–§4、`frontend/src/core/http/sseStream.ts`、`frontend/src/features/sessions/api/stream-chat.ts`、`frontend/src/features/chat/runtime/agent-runtime.ts`、`frontend/deploy/nginx/default.conf.template`
- 现状复核（2026-11-01）：Java 侧仍无 Agent 客户端——`WebClient` / `RestTemplate` / `RestClient` / Feign 在 `application-service/src` 零命中，本文决策继续有效；但 Agent 侧存在对 Java `/internal/v1/**` 的**反向调用**（`agent-service/app/services/control_plane.py`：`auth/service-token`、`model-tasks`、`model-access/check`、`model-usage`），属内部控制面，不属于本文「前端直连 Agent、Java 不代理 SSE」的决策范围

## 背景

三端需要一条统一的公网入口。对话接口 `POST /agent/api/v1/chat/stream` 是 SSE 长连接，单次可持续数分钟；若让 Java 承担转发，需要引入 WebClient/Feign 流式转发、错误透传、超时与取消的二次实现，并让 Java 感知 Agent 地址与模型错误码。

当时的约束：

1. Agent 只校验 Token、不签发 Token，用户身份由 Java 签发的 JWT 传递。
2. Java 与 Agent 使用独立数据库，不共享业务表。
3. 前端已区分两套请求封装：Java 走 axios 信封，Agent 走 `fetch` + 原生 SSE 读取。

## 备选方案

| 方案 | 做法 | 代价 |
| --- | --- | --- |
| A. Java 代理 | 前端只调 Java，Java 新增 Agent 客户端并转发 SSE | 需实现流式转发、断连取消、超时、错误映射；Java 引入对 Agent 的运行时依赖 |
| B. Nginx 直连（选中） | Nginx 暴露 `/api/` 与 `/agent/`，前端分别调用 | Nginx 需正确配置 SSE 不缓冲、长超时；两套响应格式需前端分别处理 |
| C. Agent 公网直连 | 浏览器直接访问 Agent 端口 | 暴露内部服务，鉴权与限流边界缺失 |

## 决策

采用方案 B：保留 Nginx 作为唯一公网入口，前端经 `/agent/` 直连 Agent（Nginx 剥前缀转发），Java 不新增 Agent 客户端、不代理 SSE。

配套约束（均已落地）：

- `/agent/` 关闭 `proxy_buffering` 与 `gzip`，`proxy_read_timeout` 设为长连接值；`/api/` 保持常规超时。
- Agent 只持公钥 `AUTH__JWT_PUBLIC_KEY` 校验 JWT，不建用户表、不签发生产 Token。
- 结论已写入 `docs/architecture-overview.md` §6 决策表；跨端路径与事件格式以 `docs/api-contract.md` 为准。

## 影响

- 正面：Java 不引入流式转发复杂度；模型错误码与 SSE 事件由 Agent 直接定义；前端可复用浏览器原生流式读取。
- 负面：前端需维护两套请求封装与两套错误格式；Agent 成为直接对外服务，其限流、超时与指标暴露必须由 Nginx 兜底（指标端点已加内网白名单）。
- 后续若改为 Java 代理，必须新增 ADR 并将本文标记为 `Superseded`，同时更新 `api-contract.md` 与前端请求层。

## 相关记录

- 原始决策讨论记录于 `docs/architecture-overview.md` §6（C-08）。
- 认证与令牌细节见 `docs/services/application-service/security.md`。
