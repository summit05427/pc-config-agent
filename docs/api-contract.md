# 三端 HTTP 与流式契约

| 项 | 内容 |
| --- | --- |
| 状态 | Current |
| 最后核验 | 2026-11-01 |
| 权威性 | Authoritative（对外 HTTP / SSE 契约 + 内部接口摘要） |
| 主要证据 | `application-service/**/controller/**`、`agent-service/app/api/v1/**`、`frontend/src/features/*/api/**`、`frontend/deploy/nginx/default.conf.template` |

适用范围：浏览器 ↔ Java、浏览器 ↔ Agent（均经 Nginx），以及 Agent → Java 的内网内部接口。

**两条边的方向必须分清（2026-11-01 修订）**：

- Java **不调用** Agent（2026-10-28 已确认：保持前端经 Nginx 直连 Agent，Java 不代理 SSE 流）。
- Agent **会调用** Java 的 `/internal/v1/**`（服务令牌 + 可选 `X-User-Token`），契约见 §5.6。
- 因此本文既包含对外契约，也包含内部接口摘要；内部接口的字段实现细节见 `services/application-service/api-reference.md` §8。

本文是实现级契约，冲突时以本文为准；各服务的实现细节见 `services/` 下对应文档。

## 1. 路径前缀与代理

| 调用方 | 公网路径 | 转发目标 | 上游路径 |
| --- | --- | --- | --- |
| 前端 → Java | `/api/v1/**` | `application-service:8080` | 保留前缀：`/api/v1/**` |
| 前端 → Agent | `/agent/api/v1/**` | `agent-service:8000` | 去掉 `/agent`：`/api/v1/**` |

- 两个服务的源码路径都以 `/api/v1` 开头，`/agent` 只是 Nginx 的路由前缀，不属于 Agent 自身路径。
- 前端不得写死域名或端口：Java 用 `VITE_API_BASE_URL`（默认 `/api/v1`），Agent 用 `VITE_AGENT_BASE_URL`（默认 `/agent/api/v1`），见 `frontend/src/shared/lib/env.ts`。
- `VITE_*` 在构建期写入静态产物，修改后必须重建前端镜像。

## 2. 鉴权

**双令牌模型**（2026-10-29 落地）：

| 令牌 | 形态 | 存放位置 | 有效期 |
| --- | --- | --- | --- |
| Access Token | RS256 JWT | 前端内存（刷新页面即丢失） | `JWT_ACCESS_TTL`，默认 `10m` |
| Refresh Token | 32 字节随机串（Base64URL 43 字符） | `HttpOnly` Cookie `agent_refresh`，JS 不可读 | 闲置 7 天 / 绝对 30 天（`AUTH_REFRESH_IDLE_TTL` / `AUTH_REFRESH_ABSOLUTE_TTL`） |

- Access Token 只由 Java 的 `POST /api/v1/auth/login` 与 `POST /api/v1/auth/refresh` 签发，算法 **RS256**，issuer `agent-application-service`（`JWT_ISSUER` 可覆盖）。
- 令牌头带 `kid`（`JWT_KID`）；claims 含 `sub` / `iss` / `iat` / `exp` / `aud` / `jti` / `roles` / `token_use="access"` / `sid`。`sub` 是 `users.public_id`（UUID），内部自增主键与登录名都不进令牌。`sid` 是签发时所在刷新令牌族（`refresh_sessions.family_id`），仅用于标记「当前设备会话」，不参与任何鉴权判断，Agent 验签会忽略该字段。
- Java 用私钥签发，Agent 只持公钥验签（`AUTH__JWT_PUBLIC_KEY`），两端同时使用 `JWT_KID`、`JWT_ISSUER`、`JWT_AUDIENCE`，任一不一致都会导致验签失败。
- 请求头统一：`Authorization: Bearer <access_token>`。
- Agent 校验（`agent-service/app/core/security.py`）：按 `kid` 从本进程公钥白名单选钥（未知 `kid` 直接拒绝，不远程拉取），算法只允许 `RS256`，并强制校验 `exp` / `sub` / `iss` / `aud` / `token_use="access"`；`aud` 不再可选。
- 刷新令牌只出现在 `Set-Cookie`，禁止出现在响应体、URL 或日志。Cookie 属性固定为 `HttpOnly`、`SameSite=Strict`、`Path=/api/v1/auth`，`Secure` 由 `AUTH_COOKIE_SECURE` 控制且生产强制为 `true`。
- `/api/v1/auth/refresh` 与 `/logout` 额外校验请求来源（`Origin`，缺失时退回 `Referer`）：必须命中 `CORS_ALLOWED_ORIGINS` 白名单或与请求 `Host` 同源，否则返回 403 `20002`。这是 `SameSite=Strict` 之外的服务端兜底。
- 前端遇到 401 先做**单飞刷新**（并发 401 共用一次 `/auth/refresh`），成功则带新令牌重试原请求一次；刷新失败才清理登录态并交给路由（`frontend/src/core/http/auth.ts` 统一决策，`httpJson.ts` 与 `features/sessions/api/request.ts` 各自执行重放）。`/auth/login`、`/auth/refresh` 声明 `authPolicy: 'no-redirect'`（不刷新、不跳转），`/auth/logout` 声明 `authPolicy: 'no-refresh'`（不刷新但仍清理并跳转）。
- 403 表示已认证但无权限，不触发刷新与全局退出。

Java 401/403 使用统一信封（`shared/security/SecurityResponseWriter.java`），`code` 为 `20001` / `20002`。

Agent 401 使用字符串码（`agent-service/app/core/security.py`）：

| code | HTTP | 触发条件 |
| --- | --- | --- |
| `unauthorized` | 401 | 缺少 `Authorization` 头 |
| `token_expired` | 401 | `exp` 已过期 |
| `token_invalid` | 401 | 签名、`kid`、issuer、audience、`sub`、`token_use` 任一不合法 |

## 3. 响应信封

**Java**（`shared/api/ApiResponse.java`）：所有接口统一外壳，HTTP 状态码表达协议语义，`code` 表达业务结果。

```json
{ "code": 0, "message": "ok", "data": {}, "requestId": "6f1c2f4e-..." }
```

- 成功固定 `code = 0`；`data` 为空时因 `@JsonInclude(NON_NULL)` 不输出该字段。
- `requestId` 与响应头 `X-Request-Id` 一致。
- 错误响应在信封**顶层**可选输出 `errorType`（小写蛇形字符串，如 `quota_exceeded`），供调用方做状态机分支。它只允许出现在错误响应，禁止放进 `data`：报错时 `data` 通常为空，若混在一起，调用方无法区分「该渲染数据」还是「该弹窗报错」。
- 数字 `code` 仍是 Java 的稳定契约；Agent 专属接口由 Agent 层薄 Adapter 把数字码映射成字符串码，对外保持现代化协议。

**Agent 成功响应**：裸 JSON，不使用外壳（`app/api/v1/sessions.py`、`app/api/v1/auth.py`）。

**Agent 错误响应**（`app/core/exceptions.py`）：

```json
{ "code": "session_not_found", "message": "会话不存在或尚无消息", "request_id": "..." }
```

校验失败额外带 `details: [{ "field": "...", "reason": "..." }]`，状态码 422。

前端因此有两套门面：`frontend/src/core/http/httpJson.ts` 拆 Java 信封，`frontend/src/core/http/sseStream.ts` 直接读裸 JSON 与 SSE；业务域 API 在其上封装（`frontend/src/features/*/api/**`）。禁止把两者混用。

## 4. 分页、时间与空值

| 规则 | Java | Agent |
| --- | --- | --- |
| 页码 | `page` 从 1 开始，默认 1 | 同 |
| 每页条数 | `size` 默认 20，最大 100，越界 400 | 默认 20，最大 100，越界 400（`sessions.py` 显式校验） |
| 越界错误码 | 400 `10001` 参数不合法 | 400 `invalid_pagination` |
| 列表字段 | `data.list / data.total / data.page / data.size` | 顶层 `list / total / page / size` |
| 时间格式 | ISO-8601 UTC，如 `2026-10-26T08:00:00Z` | 同（`sessions.py` 的 `_to_iso`） |
| 空集合 | 返回 `[]`，不返回 `null` | 同 |

默认值统一为 `page=1`、`size=20`（2026-10-28 决策）。前端按场景显式覆盖，取值均在服务端上限之内：

| 场景 | 取值 | 证据 |
| --- | --- | --- |
| 会话列表 | 20 | `frontend/src/features/chat/hooks/use-chat-model.ts`（`SESSIONS_PAGE_SIZE`） |
| 历史消息 | 100 | `frontend/src/features/sessions/api/queries.ts`（`HISTORY_PAGE_SIZE`） |
| 登录设备 | 5 | `frontend/src/features/settings/components/device-sessions.tsx` |
| 模型用量 | 10 | `frontend/src/features/settings/components/model-usage-panel.tsx` |

## 5. Java 接口

| 方法 | 路径 | 鉴权 | 请求 | 响应（`data`） |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/auth/login` | 放行 | `{ "username": "...", "password": "..." }`，两者均 `@NotBlank` | `{ "accessToken": "...", "tokenType": "Bearer", "expiresIn": 600, "user": { "publicId": "...", "username": "admin", "roles": ["ADMIN"] } }`，同时 `Set-Cookie: agent_refresh=...` |
| POST | `/api/v1/auth/refresh` | 放行（凭 Cookie） | 无请求体，读取 `agent_refresh` | `{ "accessToken": "...", "tokenType": "Bearer", "expiresIn": 600 }`，同时轮换 `Set-Cookie` |
| POST | `/api/v1/auth/logout` | 放行（凭 Cookie） | 无请求体 | 无 `data`；`Set-Cookie` 置 `Max-Age=0` 清除 |
| GET | `/api/v1/auth/me` | 需登录 | 无 | `{ "publicId": "...", "username": "admin", "roles": ["ADMIN"] }` |
| GET | `/api/v1/users/me/profile` | 需登录 | 无 | `{ "publicId": "...", "username": "admin", "displayName": "...", "email": "...", "bio": "...", "roles": ["ADMIN"], "status": "ACTIVE", "createdAt": "...", "updatedAt": "..." }` |
| PUT | `/api/v1/users/me/profile` | 需登录 | `{ "displayName": "...", "email": "...", "bio": "..." }`；`displayName` 去空白后 1..64，`email` 可选且 ≤255，`bio` 可选且 ≤500 | 与 GET 相同，返回更新后的最新资料 |
| PUT | `/api/v1/users/me/password` | 需登录 | `{ "currentPassword": "...", "newPassword": "..." }`；`currentPassword` ≤128，`newPassword` 8..64 | 无 `data`；成功后撤销除当前 `sid` 之外的全部刷新会话 |
| POST | `/api/v1/auth/logout-all` | 需登录 | 无 | 无 `data`；撤销该用户全部刷新会话，同时 `Set-Cookie` 置 `Max-Age=0` |
| GET | `/api/v1/users/me/sessions` | 需登录 | 查询参数 `page`、`size` | `{ "list": [{ "familyId": "...", "createdAt": "...", "lastUsedAt": null, "idleExpiresAt": "...", "absoluteExpiresAt": "...", "current": true }], "total": 2, "page": 1, "size": 20 }` |
| DELETE | `/api/v1/users/me/sessions/{familyId}` | 需登录 | 无 | 无 `data`；撤销该设备的刷新会话 |
| GET | `/api/v1/users/me/preferences` | 需登录 | 无 | `{ "instructions": "回答尽量简短", "replyLanguage": "zh-CN", "responseStyle": "concise", "useHistory": true, "updatedAt": "..." }` |
| PUT | `/api/v1/users/me/preferences` | 需登录 | 同结构（全部必填）；`instructions` 可空且 ≤1000，`replyLanguage` ∈ `auto\|zh-CN\|en-US`，`responseStyle` ∈ `concise\|balanced\|detailed`，`useHistory` 布尔 | 同上，返回保存后的最新值 |

- 登录响应直接带用户信息，前端登录后无需再请求 `/auth/me`；`publicId` 与令牌 `sub` 一致，内部自增主键不出现在任何响应里。
- `roles` 已去掉 `ROLE_` 前缀，只返回业务角色。
- `expiresIn` 单位为秒，来自 `JWT_ACCESS_TTL`（默认 `10m`）。
- `/refresh` 每次返回**新的**刷新令牌；旧令牌被标记 `rotated`。用已轮换的旧令牌重放：轮换宽限期（`AUTH_REFRESH_ROTATION_GRACE`，默认 60s）内只返回 401、不撤销令牌族，超期则整族撤销（`revoked_reason=replay`），用户需重新登录。
- `/refresh` 失败场景统一 401 `20001`：Cookie 缺失、令牌未知、已撤销、闲置/绝对过期、用户被禁用（禁用会撤销整族）。
- `/logout` 幂等：无 Cookie 或 Cookie 已失效同样返回 200 `code=0`。
- 个人资料读写固定走 `/users/me/profile`（不提供 `/users/{id}`）：只操作令牌 `sub` 对应的本人数据，天然不存在越权入口。`displayName` / `email` / `bio` 未设置时返回 `null`；三个字段在反序列化时就统一去首尾空白，`email` / `bio` 的空白值转 `NULL`，避免与 `uq_users_email` 的空串冲突。
- 邮箱与他人冲突返回 409 `40104`（`IdentityErrorCode.EMAIL_TAKEN`）：`4xxxx` 为业务模块专用区间，这是该区间首个登记的错误码。
- 改密固定走 `/users/me/password`，只认本人：当前口令错误返回 400 `40102`、新旧口令相同返回 400 `40103`。两者**刻意不用 401**，否则前端会当成登录失效触发全局登出与单飞刷新。成功后同一事务内按 `user_id` 撤销除当前 `sid` 外的全部会话（`revoked_reason=password_change`），当前设备继续可用；令牌缺少 `sid`（改造前的存量令牌，最长 10 分钟内过期）返回 401 `20001`，要求重新登录。
- 登录设备按刷新令牌族聚合：同一次登录的整条轮换链只返回一行（`GROUP BY family_id`），`createdAt` 取族内最早时间、`lastUsedAt` 取族内最近使用时间；已撤销或已过期的族不出现。`current` 由访问令牌的 `sid` 与 `family_id` 比对得出，**仅用于展示**；令牌缺少 `sid` 时全部为 `false`，不报错。
- 撤销设备时：目标是当前设备返回 409 `30002`（需改走 `/auth/logout`，以便同步清 Cookie）；族不存在或属于他人统一返回 404 `40105`，不区分两者以免泄露他人会话；`familyId` 不是合法 UUID 返回 400 `10001`。归属校验下推到 SQL 的 `user_id` 条件，避免检查与执行之间的竞态。
- `/auth/logout-all` 需要访问令牌（不走 Cookie），因此 Cookie 已失效也能成功；撤销本身幂等，重复调用不会报错，成功后浏览器回登录页。
- 用户偏好固定走 `/users/me/preferences`：从未保存过时返回默认值（`auto` / `balanced` / `useHistory=true`）且 `updatedAt=null`，不伪造保存时间；保存后由 SQL 显式写 `updated_at`。偏好是「客户端声明的用户偏好」，**不参与鉴权**，只由前端随 `POST /agent/api/v1/chat/stream` 的 `preferences` 字段携带，Agent 只做长度与枚举校验（见 §6）。
- 管理端接口：**已实现（2026-11-01）**。`SecurityConfig` 的 `/api/v1/admin/**` → `hasRole("ADMIN")` 规则已由 `AdminUserController` / `AdminAuditLogController` 承接；认证审计覆盖 8 类事件（含 `role_changed`），查询接口见 §5.1。
- 完整 DTO、错误码与过滤链细节见 `services/application-service/api-reference.md`。

### 5.1 管理端接口（已实现）

> 状态：**【已实现】（2026-11-01）**。实现见 `identity/web/{AdminUser,AdminAuditLog}Controller.java`、`identity/application/{AdminUserService,AdminAuditLogService}.java`；接口测试见 `AdminUserApiTests`、`AdminAuditLogApiTests`。模型目录与定价见 `model/web/AdminModelCatalogController.java`、`model/application/AdminModelCatalogService.java`，单测见 `AdminModelCatalogServiceTests`。用量与连接只读见 `model/web/{AdminModelUsage,AdminModelConnection}Controller.java`、`model/application/{AdminModelUsage,AdminModelConnection}Service.java`，单测见 `AdminModelUsageServiceTests`、`AdminModelConnectionServiceTests`（2026-11-02）。

所有接口均需 `Authorization: Bearer <access_token>` 且角色为 `ADMIN`；未认证返回 401 `20001`，非管理员返回 403 `20002`。响应仍使用 Java 统一信封。

| 方法 | 路径 | 鉴权 | 请求 | 响应（`data`） |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/admin/users` | `ADMIN` | 查询参数 `page`、`size`、`keyword`（用户名/邮箱模糊，≤64）、`status`（`ACTIVE\|DISABLED`） | `{ "list": [{ "publicId": "...", "username": "...", "email": "...", "roles": ["USER"], "status": "ACTIVE", "createdAt": "..." }], "total": 1, "page": 1, "size": 20 }` |
| PATCH | `/api/v1/admin/users/{publicId}/status` | `ADMIN` | `{ "status": "ACTIVE" \| "DISABLED" }` | 更新后的用户摘要（字段同上）；禁用会撤销该用户全部刷新会话 |
| PATCH | `/api/v1/admin/users/{publicId}/roles` | `ADMIN` | `{ "roles": ["USER", "ADMIN"] }`，非空、≤10 个元素；白名单仅 `USER` / `ADMIN` | 更新后的用户摘要（字段同上） |
| GET | `/api/v1/admin/audit-logs` | `ADMIN` | 查询参数 `page`、`size`、`event`（8 类事件白名单）、`username`（精确匹配，≤64） | `{ "list": [{ "event": "login_success", "username": "admin", "ip": "...", "createdAt": "..." }], "total": 1, "page": 1, "size": 20 }` |
| GET | `/api/v1/admin/models` | `ADMIN` | 查询参数 `page`、`size`、`keyword`（展示名/模型标识模糊，≤64）、`provider`（≤32）、`enabled`（`true\|false`，空串=不过滤） | `{ "list": [{ "provider": "deepseek", "modelKey": "deepseek-v4-pro", "displayName": "DeepSeek V4 Pro", "contextWindow": null, "capabilities": ["text", "tool_calling"], "capabilitySource": "MANUAL", "verifiedAt": null, "enabled": true, "providerEnabled": true, "latestPricing": { "id": 3, "currency": "USD", "inputPricePerMillion": 0.15, "outputPricePerMillion": 0.6, "effectiveFrom": "2026-11-01T00:00:00Z", "createdAt": "2026-11-01T02:00:00Z" } }], "total": 3, "page": 1, "size": 20 }`；`latestPricing` 无定价时为 `null` |
| PATCH | `/api/v1/admin/models/{provider}/{modelKey}/status` | `ADMIN` | `{ "enabled": true }` | 更新后的模型摘要（字段同上） |
| GET | `/api/v1/admin/models/{provider}/{modelKey}/pricing` | `ADMIN` | 查询参数 `page`、`size` | `{ "list": [{ "id": 3, "currency": "USD", "inputPricePerMillion": 0.15, "outputPricePerMillion": 0.6, "effectiveFrom": "...", "createdAt": "..." }], "total": 2, "page": 1, "size": 20 }`，按 `effectiveFrom` 倒序 |
| POST | `/api/v1/admin/models/{provider}/{modelKey}/pricing` | `ADMIN` | `{ "currency": "USD", "inputPricePerMillion": 0.15, "outputPricePerMillion": 0.6, "effectiveFrom": "2026-11-01T00:00:00Z" }`；`currency` 3 位字母、缺省 `USD`；单价 `@DecimalMin(0)` 且最多 12 位整数 / 6 位小数；`effectiveFrom` 必填 | 新增的定价版本（结构同上） |
| GET | `/api/v1/admin/model-providers` | `ADMIN` | 无 | `[{ "code": "deepseek", "displayName": "DeepSeek", "protocol": "openai-compatible", "defaultBaseUrl": null, "enabled": true, "modelCount": 3, "enabledModelCount": 2 }]`，按 `code` 升序，不分页 |
| PATCH | `/api/v1/admin/model-providers/{code}/status` | `ADMIN` | `{ "enabled": true }` | 更新后的 Provider 摘要（字段同上） |
| GET | `/api/v1/admin/model-usage` | `ADMIN` | 查询参数 `page`、`size`、`userId`（UUID，≤36）、`provider`（≤32）、`modelKey`（≤64）、`credentialSource`（`MANAGED\|BYOK`）、`costStatus`（`ESTIMATED\|UNKNOWN\|BYOK_NOT_BILLED`）、`status`（`success\|failure`）、`from` / `to`（`YYYY-MM-DD`，UTC 自然日闭区间）、`order`（`asc\|desc`，默认 `desc`）；空串=不过滤 | `{ "list": [{ "invocationId": "...", "taskId": "...", "userId": "...", "username": "...", "threadId": "...", "modelRole": "...", "provider": "deepseek", "modelKey": "deepseek-v4-pro", "credentialSource": "MANAGED", "promptTokens": 120, "completionTokens": 80, "latencyMs": 950, "status": "success", "errorType": null, "estimatedCost": 0.0001, "costStatus": "ESTIMATED", "costBearer": "PLATFORM", "currency": "USD", "occurredAt": "2026-11-01T08:00:00Z" }], "total": 1, "page": 1, "size": 20 }`；按 `occurredAt` 排序 |
| GET | `/api/v1/admin/model-usage/summary` | `ADMIN` | 查询参数 `provider`、`modelKey`、`credentialSource`、`from`、`to`（口径同明细；**不支持** `userId` / `costStatus` / `status`，避免卡片与列表口径不一致） | `{ "from": null, "to": null, "totals": { "requestCount": 1, "successCount": 1, "failureCount": 0, "promptTokens": 120, "completionTokens": 80, "totalTokens": 200, "estimatedCost": 0.0001, "currency": "USD", "estimatedCount": 1, "unknownCostCount": 0, "byokNotBilledCount": 0 }, "byCostStatus": [{ "costStatus": "ESTIMATED", "requestCount": 1, "estimatedCost": 0.0001, "currency": "USD" }], "byProvider": [{ "provider": "deepseek", "requestCount": 1, "promptTokens": 120, "completionTokens": 80, "totalTokens": 200, "estimatedCost": 0.0001, "currency": "USD" }], "byModel": [{ "provider": "deepseek", "modelKey": "deepseek-v4-pro", "requestCount": 1, "promptTokens": 120, "completionTokens": 80, "totalTokens": 200, "estimatedCost": 0.0001, "currency": "USD" }] }`；`byProvider` / `byModel` 按调用量倒序，最多 20 条 |
| GET | `/api/v1/admin/model-connections` | `ADMIN` | 查询参数 `page`、`size`、`userId`（UUID，≤36）、`provider`（≤32）、`status`（`ACTIVE\|DELETED`）；空串=不过滤 | `{ "list": [{ "id": "...", "userId": "...", "username": "demo", "displayName": "演示账号", "provider": "deepseek", "providerName": "DeepSeek", "baseUrl": "https://api.deepseek.com/v1", "status": "ACTIVE", "lastVerifiedAt": "2026-11-01T09:00:00Z", "createdAt": "2026-11-01T08:00:00Z", "credential": { "id": "...", "maskedHint": "sk-****abcd", "status": "VERIFIED", "createdAt": "2026-11-01T08:00:00Z" } }], "total": 1, "page": 1, "size": 20 }`；**只读**，无凭证时 `credential` 为 `null`，任何情况下都不返回密文或明文 |

约束与错误码：

- 审计事件白名单：`login_success` / `login_failure` / `refresh_replay` / `logout` / `logout_all` / `password_change` / `user_disabled` / `role_changed`；审计表不记录口令、Token、Cookie。
- 不能禁用当前登录的管理员自己，返回 409 `30002`；角色变更后系统必须仍有至少一个启用的 `ADMIN`，否则 409 `30002`。
- 分页 `page ≥ 1`、`size` 1..100；`status`、`roles`、`event` 枚举非法或 `publicId` 非 UUID 返回 400 `10001`；目标用户不存在返回 404 `30001`。
- 登录失败限流：**已实现（2026-10-31）**。同一「客户端 IP + 用户名」60 秒窗口内认证失败 5 次后，第 6 次登录返回 429 `10007`；仅统计认证失败，成功登录清零。客户端 IP 依次取 `X-Forwarded-For` 首段、`X-Real-IP`、`remoteAddr`。当前为进程内实现，**仅单实例有效**；多副本部署需替换为共享存储（如 Redis）实现，接口层无需改动。
- 模型目录只能启停、不可删除：历史用量台账以 `provider + modelKey` 引用目录条目，删除会破坏追溯。
- 停用 Provider 后其下模型即使 `enabled=true` 也不可用；模型列表用 `providerEnabled=false` 明示该状态，管理端仍可单独调整模型开关，恢复 Provider 后即生效。
- 标识格式：`provider` 必须匹配 `^[a-z0-9][a-z0-9-]{0,31}$`，`modelKey` 必须匹配 `^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$`；格式非法 400 `10001`，模型或 Provider 不存在 404 `30001`。
- 定价只追加版本、不修改既有记录：成本在用量入库时按当时生效的版本定格，后续调价不回算历史台账（§5.4）。
- 同一 `(provider, modelKey, effectiveFrom)` 重复提交返回 409 `40221`；并发插入由表上的 `UNIQUE(provider, model_key, effective_from)` 兜底，同样转 409。
- 启停接口幂等：目标状态与当前一致时不写库，直接返回当前摘要。
- `latestPricing` 取 `effectiveFrom` 最新的一条，缺失时为 `null`；此时新调用成本仍记 `UNKNOWN`，需运营补录定价。
- 用量与聚合统一按 **UTC 自然日** 解释 `from` / `to`（闭区间，服务端把 `to` 转成次日零点开区间）；`from > to` 返回 400 `10001`，`userId` 非 UUID 同样 400。
- 多币种不求和：聚合结果中若估算费用涉及多个币种，则 `estimatedCost` 与 `currency` 统一置 `null`，前端展示「多币种」；`currencyCount` 只在内部用于判断，不对外输出。
- 聚合的 `byProvider` / `byModel` 最多返回 20 条（按调用量倒序），不做分页；明细列表才提供完整分页。
- 管理端连接视图**只读**：不提供创建、验证、删除入口；SQL 只选 `masked_hint` 与凭证状态，响应不包含 `ciphertext`、明文密钥或密钥版本。

### 5.2 模型目录（2026-10-30 已实现，PR1）

| 方法 | 路径 | 鉴权 | 请求 | 响应（`data`） |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/models` | 需登录（`token_use=access`） | 无 | `[{ "provider": "deepseek", "modelKey": "deepseek:deepseek-v4-pro", "displayName": "DeepSeek 4.1 Pro", "capabilities": ["text", "tool_calling"], "contextWindow": 128000, "credentialSource": "MANAGED" }]` |

- `modelKey` 是完整引用 `<provider>:<modelKey>`，与 Agent 侧请求的 `model` 字段取值一致；`null` 表示 Auto。
- `capabilities` 是开放字符串数组，未知值必须忽略，禁止按 Provider 推断能力。当前约定：`text`（可对话）、`tool_calling`（支持工具调用）、`reasoning`（可产生思考，可被请求开启）、`reasoning_visible`（思考文本会经 SSE `reasoning` 事件下发，前端可展示）。`reasoning_visible` 只在同时具备 `reasoning` 时出现；OpenAI 推理类模型只有 reasoning tokens、无可展示文本，因此只标 `reasoning`。
- `/api/v1/models` 只返回**平台托管模型**（`models.byok_only=false`）；`MODEL_MANAGED_ENABLED=false`（纯 BYOK 部署）或平台密钥探测失败时返回空数组。平台密钥是否可用由 `ManagedModelAvailability` 通过网关 `probe:<provider>` 真实探测，不再只判断配置项是否非空；BYOK 专用模型按用户可见性由 v2 返回，见 §5.5。
- `credentialSource` 表示该模型本次会使用的凭证来源：`MANAGED`（平台托管）或 `BYOK`（用户自带密钥）；判定规则与运行时一致——该 Provider 存在可用 BYOK 连接即为 `BYOK`。
- `errorType` 只在错误响应顶层输出。运行时未启用（`MODEL_RUNTIME_ENABLED=false`）返回 404 `40204`、`errorType=runtime_disabled`，前端据此隐藏模型选择、回退单模型 UI。
- Agent 经内部接口 `/internal/v1/**` 取用目录、任务与凭证，只接受服务令牌（`token_use=service`）；用户令牌访问内部接口返回 401，服务令牌访问 `/api/v1/**` 同样返回 401。内部接口全部契约见 §5.6。

### 5.3 模型连接与凭证（BYOK，2026-10-30 已实现，PR4）

需登录（`token_use=access`），用户身份只取令牌 `sub`，不接受请求体中的用户字段。**任何接口都不回显明文密钥，也不存在 `/credentials` 回读端点**；响应中的凭证只有掩码与状态。

| 方法 | 路径 | 请求 | 响应（`data`） |
| --- | --- | --- | --- |
| GET | `/api/v1/model-connections` | 无 | `[{ "id": "...", "provider": "deepseek", "providerName": "DeepSeek", "baseUrl": "https://api.deepseek.com/v1", "status": "ACTIVE", "lastVerifiedAt": null, "createdAt": "...", "credential": { "id": "...", "maskedHint": "sk-****7890", "status": "UNVERIFIED", "createdAt": "..." } }]`，按创建时间倒序 |
| POST | `/api/v1/model-connections` | `{ "providerCode": "deepseek", "baseUrl": "https://... （可空）", "apiKey": "sk-..." }`；`apiKey` 8..512 字符 | 新建连接（结构同上）；写入后**自动验证一次**：成功时 `credential.status=VERIFIED` 且 `lastVerifiedAt` 有值；上游明确拒绝时置为 `INVALID` 并清空 `lastVerifiedAt`；网络不可达时保留 `UNVERIFIED`（不回滚已保存的连接） |
| PUT | `/api/v1/model-connections/{connectionId}` | `{ "baseUrl": "https://... （可空，留空沿用原地址）", "apiKey": "sk-..." }` | 轮换凭证：旧凭证撤销为 `REVOKED`、写入新凭证，清空旧的 `lastVerifiedAt`，保存后自动验证一次（响应结构同上） |
| POST | `/api/v1/model-connections/{connectionId}/verify` | 无 | 手动重新验证：按 Provider 协议做真实探测：OpenAI 兼容用 `Authorization: Bearer` + `GET /models`，Anthropic 用 `x-api-key`/`anthropic-version` + `/v1/models`；列表端点 404/405/501 时退化为 `max_tokens=1` 的最小对话，成功写 `lastVerifiedAt` 并把凭证置为 `VERIFIED`；凭证被拒时置为 `INVALID` 并返回 422 `40219`，上游不可用 502 `40217`（不改状态）、超过单用户验证频率 429 `40222`（默认 5 次/分钟，见 `MODEL_CRED_VERIFY_RATE_LIMIT_PER_MINUTE`） |
| DELETE | `/api/v1/model-connections/{connectionId}` | 无 | `data` 为空；连接软删除为 `DELETED`、凭证撤销为 `REVOKED`，撤销后凭证不可再使用 |

约束与错误码：

- 密文格式 `v1:<key_version>:<base64(nonce|tag|ciphertext)>`，AES-256-GCM，每次加密使用独立 12 字节 nonce；主密钥 `MODEL_CRED_MASTER_KEY` 只注入 Java，禁止下发给 Agent 或前端。
- 轮换期可配置多版本密钥环 `MODEL_CRED_MASTER_KEYS`（`<version>:<base64>`，多项英文逗号分隔），按密文中的 `key_version` 选择密钥，旧版本密文仍可解密；未配置时退回单密钥模式。
- 同一用户同一 Provider 仅允许一条 `ACTIVE` 连接（部分唯一索引）；重复创建返回 409 `40212`。删除后可重新创建。
- `baseUrl` 留空使用 Provider 默认地址；只接受 `http`/`https` 且必须含 host，超长 255。
- 出站地址同时做字面量与 DNS 校验：域名解析出的地址中只要有一条落在回环、私网、链路本地、CGNAT、组播或 IPv6 ULA 等禁止网段，即拒绝为 `40214`；解析结果被拒绝时不发起请求，可防 DNS rebinding 到内网。
- 归属校验下推到 SQL：访问他人连接与不存在等价，统一返回 404 `40210`。
- 错误码：`40209` BYOK 未启用（404）、`40210` 连接不存在或不属于当前用户（404）、`40211` Provider 不存在或不受支持（400）、`40212` 连接已存在（409）、`40213` 凭证损坏（500，需重新录入）、`40214` 接入地址非法（400）、`40222` 验证频率超限（429）、`40223` 未提供密钥（400）。
- 审计：创建、轮换、验证成功/失败、删除凭证都会写入 `auth_audit_logs`，事件名分别为 `model_credential_created`、`model_credential_updated`、`model_credential_verified`、`model_credential_verify_failed`、`model_credential_deleted`；审计失败不阻断业务。
- 开关 `BYOK_ENABLED=false` 时全部接口返回 404 `40209`，前端据此隐藏「模型与密钥」配置；回滚策略即关闭该开关。前端只把 `40209`（及运行时总开关 `40204`）识别为「未启用」，其它错误按加载失败展示重试入口。

### 5.4 模型用量（2026-10-31 已实现，PR6）

需登录（`token_use=access`），用户身份只取令牌 `sub`；固定路径 `/users/me/model-usage`，不提供按用户 ID 查询的入口，因此不存在越权路径。

| 方法 | 路径 | 请求 | 响应（`data`） |
| --- | --- | --- | --- |
| GET | `/api/v1/users/me/model-usage` | 查询参数 `page`（默认 1）、`size`（默认 20，最大 100）、`from` / `to`（可选，`YYYY-MM-DD`，按 UTC 自然日） | `{ "quota": { "quotaType": "daily_requests", "limit": 100, "used": 3, "resetAt": "2026-11-01T00:00:00Z" }, "list": [{ "invocationId": "...", "taskId": "...", "threadId": "t-demo", "modelRole": "conversation", "provider": "deepseek", "modelKey": "deepseek:deepseek-v4-pro", "credentialSource": "MANAGED", "promptTokens": 120, "completionTokens": 30, "latencyMs": 850, "status": "success", "errorType": null, "costStatus": "ESTIMATED", "costBearer": "PLATFORM", "currency": "USD", "estimatedCost": 0.000036, "occurredAt": "2026-10-30T08:00:00Z" }], "total": 5, "page": 1, "size": 20, "totalTokens": 150 }` |

- 额度快照取 UTC 当日：当日尚无额度行时 `used=0`、`limit` 回落到 `MODEL_QUOTA_DAILY_REQUESTS`、`resetAt` 为次日 00:00Z。
- 明细按 `occurredAt` 倒序；`from` / `to` 是闭区间自然日，服务端转成 `[from 00:00Z, to+1 00:00Z)` 的半开区间。
- `totalTokens` 是该用户全时段累计值（`promptTokens + completionTokens`，空值按 0 计），**不受** `from` / `to` 过滤影响；无记录时为 0。
- `page < 1`、`size` 不在 1..100、或 `from > to` 返回 400 `10001`；运行时未启用返回 404 `40204`（`errorType=runtime_disabled`）。
- `promptTokens` / `completionTokens` / `latencyMs` 在上游未提供时为 `null`，不填 0 或估算值。
- 成本字段由 Java 依据 `model_pricing` 定价表在入库时计算，Agent 不上报费用：
  - `costStatus=ESTIMATED`：`estimatedCost`（每百万 token 单价 × 用量）与 `currency` 非空；
  - `costStatus=UNKNOWN`：缺定价或缺任一 token 用量，金额与币种为 `null`，不写 0 冒充已知成本；
  - `costStatus=BYOK_NOT_BILLED`：用户自带凭证，平台不承担费用，金额与币种为 `null`；
  - `costBearer` 表示成本承担方：`PLATFORM`（平台托管）或 `USER`（自带凭证）。
- 该接口由浏览器直连 Java；Agent 不参与，也不需要新增 Agent Schema。

### 5.5 分页读取（v2，2026-10-31 已实现）

前端已于 2026-11-01 切到 v2 分页读取（`page=1`、`size=100`，消费 `list`）；v1 的 `/api/v1/models` 与 `/api/v1/model-connections` 仍返回全量数组，仅作旧客户端兼容与回滚保留。v2 只新增分页读取，不重复创建、验证、删除等写入口。

| 方法 | 路径 | 查询参数 | 响应（`data`） |
| --- | --- | --- | --- |
| GET | `/api/v2/models` | `page`（默认 1）、`size`（默认 20，1..100） | `{ "list": [...同 §5.2 条目...], "total": 3, "page": 1, "size": 20 }` |
| GET | `/api/v2/model-connections` | 同上 | `{ "list": [...同 §5.3 列表条目...], "total": 1, "page": 1, "size": 20 }`，按创建时间倒序 |
| GET | `/api/v2/model-providers` | 无（固定小集合，不分页） | `[{ "code": "anthropic", "displayName": "Anthropic Claude", "protocol": "anthropic-messages", "defaultBaseUrl": "https://api.anthropic.com", "modelCount": 2 }]`，按 `code` 升序 |

- `/api/v2/models` 返回**当前用户可见**模型：平台托管模型（`byok_only=false`，且平台密钥真实探测可用）+ 用户已存在 `ACTIVE` 且凭证未被撤销/拒绝的连接所属 Provider 的 BYOK 专用模型（`byok_only=true`）。未接入 Provider 的用户不会看到对应模型；平台密钥失效或纯 BYOK 部署下目录为空时前端引导用户先配置 API Key。
- 上游调用返回鉴权类错误时，使用明细上报会把 BYOK 凭证置为 `INVALID`，或立即使平台托管缓存失效，下一次目录请求即隐藏对应模型。
- `credentialSource` 随每条模型返回，取值 `MANAGED` / `BYOK`；前端据此标注「平台」或「我的密钥」。
- `/api/v2/model-providers` 是设置页「添加供应商」的唯一数据源，只返回协议受支持且已启用的 Provider；不得从模型目录反推供应商。
- 协议白名单：`openai-compatible`（OpenAI、DeepSeek、Qwen、Volcengine、Gemini 官方兼容端点）与 `anthropic-messages`（Anthropic 原生 Messages）。
- 分页参数非法（`page < 1` 或 `size` 超出 1..100）返回 400 `10001`，不静默截断。
- 运行时未启用时 `/api/v2/models` 与 `/api/v2/model-providers` 返回 404 `40204`；BYOK 未启用时 `/api/v2/model-connections` 返回 404 `40209`。
- 页码超出总数时返回空 `list` 与真实 `total`，不返回 404。

### 5.6 内部接口（Agent → Java，`/internal/v1/**`）

这些接口只允许 Agent 经**容器内网**直连 Java，**不经 Nginx**，不对外暴露；公网访问应返回 401。

**鉴权规则（已验证，`application-service/**/security/**`）**：

- 统一使用服务令牌（`token_use=service`，`sub` 为服务客户端标识，默认 `agent-service`），由 `POST /internal/v1/auth/service-token` 用 `INTERNAL_AUTH_CLIENT_ID` / `INTERNAL_AUTH_CLIENT_SECRET` 换取，有效期 `INTERNAL_AUTH_TOKEN_TTL`（默认 `5m`）。
- 涉及用户维度的接口还需 `X-User-Token`（用户自己的 Access Token），Java 据此解析 `user_id` 做归属与额度判断；服务令牌本身不被当作用户身份。
- 用户令牌访问 `/internal/v1/**` 返回 401；服务令牌访问 `/api/v1/**` 返回 401。
- `MODEL_RUNTIME_ENABLED=false` 时 `/internal/v1/**` 返回 404 `40204`（`errorType=runtime_disabled`）。

| 方法 | 路径 | 额外鉴权 | 用途 |
| --- | --- | --- | --- |
| POST | `/internal/v1/auth/service-token` | 客户端凭据（无需 Bearer） | 换取服务令牌，scope 限定 `/internal/v1/**` |
| POST | `/internal/v1/model-tasks` | 服务令牌 + `X-User-Token`；可选 `Idempotency-Key`（1~64 字符，`[A-Za-z0-9._:-]`） | 创建模型运行时任务，原子扣减每日额度；返回 provider / modelKey / credentialSource / 过期时间 / `capabilities` 能力位 |
| GET | `/internal/v1/model-tasks/{taskId}` | 服务令牌 | 读取任务；不存在或已过期返回 404 `40206` |
| POST | `/internal/v1/model-tasks/{taskId}/credential-lease` | 仅服务令牌（不要求 `X-User-Token`） | 一次性兑换 BYOK 明文凭证，明文只在响应体出现一次 |
| POST | `/internal/v1/model-access/check` | 服务令牌 + `X-User-Token` | 校验用户是否可使用指定模型（会话级模型设置前调用） |
| POST | `/internal/v1/model-usage` | 服务令牌 + `X-User-Token` | 上报单次调用用量（token 数、延迟、状态）；Java 为用量台账唯一事实源 |

任务创建幂等：同 `(用户, Idempotency-Key)` 重放返回原任务且不重复扣额度；同键但 `threadId` / `model` 不同或原任务已过期返回 409 `40220`。幂等窗口 = `MODEL_TASK_TTL`（默认 10 分钟），过期任务由清理 Job 置为 `EXPIRED`（不物理删除，`model_usage_records` 外键仍引用）。

lease 端点错误：任务过期或撤销 404 `40206`、任务已兑换 409 `40215`、非 BYOK 任务 409 `40218`、凭证已撤销 401 `40216`、凭证被 Provider 拒绝 422 `40219`、上游不可用 502 `40217`。

字段级 DTO 与校验规则见 `services/application-service/api-reference.md` §8；Agent 侧调用实现见 `agent-service/app/services/control_plane.py`。

### 5.7 PC 配置（`/internal/v1/pc/**`）

同样只允许 Agent 经容器内网直连，鉴权沿用服务令牌 + `X-User-Token`。金额全部为整数分（`*Fen`）。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/internal/v1/pc/hardware/candidates?category=` | 返回候选硬件摘要，含 `priceFen`（最低可用报价，无报价为 `null`）与 `missingFields`（兼容性关键字段缺失项） |
| GET | `/internal/v1/pc/hardware/{hardwareId}` | 单条硬件详情，含规格与数据质量状态 |
| GET | `/internal/v1/pc/benchmarks?category=&hardwareId=` | PassMark 跑分；无数据返回空结果，不猜测分数 |
| GET | `/internal/v1/pc/offers?category=&hardwareId=&verifiedOnly=` | 报价列表，`verifiedOnly=true` 时只返回 `priceSource=OWNER_VERIFIED` |
| POST | `/internal/v1/pc/builds/compose` | 按调用方给定的 8 类硬件生成方案并落快照；请求体 `{"components":{八类硬件标识},"budgetMaxFen":可选}` |
| POST | `/internal/v1/pc/builds/validate` | 复核完整性与兼容性，返回 `checks[]`、`overallStatus`、`ruleVersion` |
| POST | `/internal/v1/pc/builds/validate-partial` | 任意已选组件子集的部分兼容性校验；不落库、不需用户令牌 |
| GET | `/internal/v1/pc/builds/{buildId}` | 读取快照；仅所属用户可见，越权返回 403 `40302` |

`compose` 只接受八个 `@NotBlank` 硬件标识与可选 `budgetMaxFen`（整数分，`>=1`，为空表示不限预算），不携带其他需求，按默认画像（`GENERAL`）生成；价格与总价只来自报价库的最低有效报价，逐件理由由服务端确定性生成，成功响应即方案详情并写入 append-only 快照。预算由服务端在写快照前强制校验，总价大于 `budgetMaxFen` 即失败，不放宽预算。失败语义：缺类别或类别不符 400 `40303`、任一选中硬件无可用报价 409 `40307`、兼容性存在硬冲突 422 `40308`、超出预算 422 `40309`，四种失败都不落库。响应 `requirements` 回显 `workloadProfile` 与 `renderMode`，响应顶层含 `scoringVersion`。

方案选型（选择哪套配置）由 Agent 侧的 LLM 决策，Java 不再提供求解端点；Java 只保留候选、最低有效价、草稿组装、兼容性校验与快照这些事实能力。

报价字段含 `priceSource`：`OWNER_VERIFIED` 为人工核验价，`MOCK_DEMO` 为演示占位价。**`MOCK_DEMO` 不得在用户侧表述为已核验报价**，前端与 `response_generator` 必须显式标注。

兼容性状态为 `PASS` / `WARNING` / `FAIL` / `UNKNOWN`。参数缺失时必须返回 `UNKNOWN`，不得降级为 `PASS`。每条 `checks[]` 额外携带 `riskLevel`（`BLOCKING` / `ADVISORY`）：`BLOCKING` 表示该字段缺失时方案不得标记为完全验证通过，但不阻断生成方案。

`validate-partial` 只执行「依赖类别全部已选」的规则，未覆盖的规则不出现在 `checks[]`；无可执行规则时 `overallStatus=UNKNOWN`，不得当 `PASS`；字段缺失同样返回 `UNKNOWN` 并回填 `missingFields`（形如 `cpu.socket`）。状态集合与 `/validate` 相同，因此 PSU 余量不足等情况仍返回 `WARNING`。

#### 5.7.1 候选、跑分与报价响应字段

| 接口 | `data` 字段 |
| --- | --- |
| `GET /hardware/candidates` | `catalogVersion`、`total`、`list[]`；条目含 `hardwareId`、`category`、`brand`、`modelName`、`displayName`、`specifications`、`specSummary`、`dataQualityStatus`、`lifecycleStatus`、`recommendationStatus`、`priceFen`（最低可用报价，无报价为 `null`）、`missingFields` |
| `GET /hardware/{hardwareId}` | 单个硬件对象，字段同上；不存在返回 404 `40301` |
| `GET /benchmarks` | `total`、`list[]`；条目含 `hardwareId`、`benchmarkType`、`score`、`secondaryScore`、`rankNo`、`samples`、`matchMethod`、`matchConfidence`、`sourceName` |
| `GET /offers` | `dataStatus`、`priceUnit`（固定 `CNY_FEN`）、`verifiedOfferCount`、`mockOfferCount`、`total`、`list[]`；条目含 `offerId`、`hardwareId`、`category`、`matchStatus`、`priceFen`、`priceType`、`priceSource`、`verifiedPrice`、`platform`、`seller`、`shopName`、`title`、`platformSku`、`purchaseUrl`、`verifiedAt`、`validUntil`、`notes` |

`verifiedOfferCount` 只统计 `priceSource=OWNER_VERIFIED`；`PLATFORM_OBSERVED` 与 `MOCK_DEMO` 都不计入已核验，`mockOfferCount` 实际返回「非 `OWNER_VERIFIED`」条数。参数 `category` / `hardwareId` 均可选，未知 `category` 返回 400 `10001`。

#### 5.7.2 `compose` / `validate` 响应结构

| 对象 | 字段 |
| --- | --- |
| `build` | `buildId`、`requirements`、`components[]`、`totalPriceFen`、`budgetMaxFen`、`budgetStatus`、`compatibilityReport`、`solverVersion`、`compatibilityRuleVersion`、`scoringVersion`、`catalogVersion`、`offerDataStatus`、`verifiedOfferCount`、`demoOfferCount`、`componentReasons[]`、`reasonSummary`、`createdAt` |
| `requirements` | `budgetMaxFen`、`scenario`、`workloadProfile`、`renderMode`、`scoringVersion`、`preference`、`minMemoryGb`、`minStorageGb`、`requireVerifiedOffers` |
| `components[]` | `category`、`hardwareId`、`brand`、`modelName`、`specSummary`、`imageUrl`、`title`、`priceFen`、`priceSource`、`priceType`、`verifiedPrice`、`purchaseUrl`、`platform`、`seller`、`offerId`、`matchStatus`、`verifiedAt`、`validUntil`、`benchmarkType`、`benchmarkScore` |
| `componentReasons[]` | `hardwareCategory`、`hardwareId`、`reason`、`scoreContribution`、`priceFen`；理由由 Java 确定性生成 |
| `compatibilityReport` | `ruleVersion`、`overallStatus`（`PASS`/`WARNING`/`FAIL`/`UNKNOWN`）、`hasFailure`、`checks[]`；check 含 `ruleId`、`ruleName`、`status`、`message`、`riskLevel`、`hardwareIds[]` |
| `budgetStatus` | `WITHIN_BUDGET` / `NO_BUDGET`；超出预算直接失败，不返回方案 |

`compose` 失败语义：缺类别或类别不符 400 `40303`、任一硬件无可用报价 409 `40307`、兼容性硬冲突 422 `40308`、超出预算 422 `40309`；四种失败都不落库。`GET /builds/{buildId}` 不存在或不属于当前用户统一 404 `40302`。

### 5.8 消息反馈（2026-11-10 已实现）

> 实现见 `feedback/web/{MessageFeedbackController,AdminFeedbackController}.java`、`feedback/application/MessageFeedbackService.java`；迁移 `V25__create_message_feedback.sql`；接口测试见 `MessageFeedbackApiTests`、`AdminFeedbackApiTests`。

消息身份由 Agent 下发（见 §6 与 §7）：`message_id` 形如 `{thread_id}:{seq}`，`seq` 是会话内消息序号。Java 不反查 Agent，只校验格式并把反馈绑定到提交者本人，表中不存对话正文。

| 方法 | 路径 | 鉴权 | 请求 | 响应（`data`） |
| --- | --- | --- | --- | --- |
| PUT | `/api/v1/messages/{messageId}/feedback` | 需登录 | `{ "threadId": "...", "rating": "UP\|DOWN", "reasonCode": "INACCURATE\|OFF_TOPIC\|INCOMPLETE\|FORMAT\|UNSAFE\|OTHER", "comment": "..." }`；`threadId` 1..64、`reasonCode`/`comment` 可选且 `comment` ≤500 | `{ "messageId": "...", "rating": "DOWN", "reasonCode": "OFF_TOPIC", "comment": "..." }` |
| DELETE | `/api/v1/messages/{messageId}/feedback` | 需登录 | 无 | 无 `data`；删除本人对该消息的评价 |
| GET | `/api/v1/feedback?threadId=...` | 需登录 | 查询参数 `threadId` | `{ "list": [{ "messageId": "...", "rating": "UP", "reasonCode": null, "comment": null }] }`，只含本人评价 |
| GET | `/api/v1/admin/feedback` | `ADMIN` | 查询参数 `page`、`size`、`rating`、`reasonCode`、`userId`、`threadId`、`from`、`to`（`yyyy-MM-dd`，左闭右开） | `{ "list": [{ "userId": "...", "username": "demo", "threadId": "...", "messageId": "...", "rating": "DOWN", "reasonCode": "OFF_TOPIC", "comment": "...", "createdAt": "..." }], "total": 1, "page": 1, "size": 20 }` |
| GET | `/api/v1/admin/feedback/summary` | `ADMIN` | 同上过滤参数（不含分页） | `{ "upCount": 30, "downCount": 10, "reasons": [{ "reasonCode": "INACCURATE", "label": "信息不准确", "total": 6 }] }` |
| GET | `/api/v1/admin/feedback/export` | `ADMIN` | 同上过滤参数 | `text/csv;charset=UTF-8` 附件，含 UTF-8 BOM 与中文表头；单次上限 10000 行，单元格以 `= + - @` 开头时前置 `'` 防公式注入 |

- 一人一消息一条评价：唯一键 `(user_id, message_id)`，重复 PUT 覆盖并刷新 `updated_at`，不做乐观锁。
- `rating=UP` 时服务端把 `reasonCode` 与 `comment` 归一化为 `null`，避免出现「点赞但带差评原因」的矛盾数据。
- 删除不存在的评价返回 404 `40402`；`messageId` / `threadId` 格式非法返回 400 `40401` / `40405`；评分与原因非法返回 400 `40403` / `40404`。
- 反馈只记录 ID、评分与备注，**不含对话正文**；排查问题需用 `thread_id` 回查 Agent 会话。

## 6. Agent 接口

所有路径均在 `/api/v1` 下；下表「公网路径」已包含 `/agent` 前缀。

| 方法 | 公网路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| GET | `/agent/api/v1/health` | 无 | 兼容旧路径，等同 `health/live` |
| GET | `/agent/api/v1/health/live` | 无 | 返回 `{status, env, service, redis}`，不依赖外部服务 |
| GET | `/agent/api/v1/health/ready` | 无 | 依赖就绪返回 200，否则 503，`dependencies` 细分 checkpointer / redis |
| GET | `/agent/api/v1/metrics` | 网关白名单 | Prometheus 文本；`METRICS__ENABLED=false` 时 404 `metrics_disabled`；配置 `METRICS__TOKEN` 后还需 `X-Metrics-Token`，否则 403 `metrics_forbidden` |
| POST | `/agent/api/v1/auth/dev-token` | 无 | 仅 `APP_ENV=dev` 且 `DEBUG=true`；否则 403 `forbidden` |
| POST | `/agent/api/v1/chat/stream` | 需登录 | SSE 对话流，见第 7 节 |
| GET | `/agent/api/v1/sessions` | 需登录 | 会话列表，查询参数 `archived`（默认 `false`）；按置顶优先、最近活跃倒序，含标题、`model_key`、`is_pinned` 与 `is_archived` |
| PATCH | `/agent/api/v1/sessions/{thread_id}` | 需登录 | 重命名会话，body `{ "title": "..." }` |
| PUT | `/agent/api/v1/sessions/{thread_id}/pin` | 需登录 | 置顶/取消置顶，body `{ "pinned": true }` |
| PUT | `/agent/api/v1/sessions/{thread_id}/archive` | 需登录 | 归档/恢复，body `{ "archived": true }` |
| PUT | `/agent/api/v1/sessions/{thread_id}/model` | 需登录 | 设置会话级模型，body `{ "model_key": "deepseek:deepseek-v4-pro" }`，`null` 表示 Auto |
| DELETE | `/agent/api/v1/sessions/{thread_id}` | 需登录 | 删除会话（元数据 + 消息 + checkpoint），204 |
| GET | `/agent/api/v1/sessions/{thread_id}/messages` | 需登录 | 历史消息，按窗口分页，支持 `order=asc\|desc`；每条消息携带稳定 `message_id`（`{thread_id}:{seq}`），用于消息反馈绑定 |

**指标端点防护**（2026-10-28 决策：网关为主、应用内兜底）：`frontend/deploy/nginx/default.conf.template` 与 `agent-service/deploy/nginx/agent.conf` 都用精确 location `= /agent/api/v1/metrics` 只放行 `127.0.0.1` 与私有网段，其余 `deny all`；应用内再校验可选的 `X-Metrics-Token`，避免网关规则漏配时指标直接对外。

**开发令牌**：请求 `{ "user_id": "...", "expires_minutes": 60 }`（1..1440），响应裸 JSON `{ "access_token": "...", "token_type": "Bearer", "expires_in": 3600 }`。

**会话列表**：

```json
{ "list": [{ "thread_id": "3f0c...", "title": "帮我查一下天气", "model_key": "deepseek:deepseek-v4-pro", "last_active_at": "2026-10-26T08:00:00Z", "is_pinned": false, "is_archived": false }], "total": 1, "page": 1, "size": 20 }
```

数据源是 Postgres 表 `session_meta`（2026-10-29 起，`app/services/session_store/postgres.py`）；`title` 取首条用户消息前 40 个字符，尚未生成时为 `null`；`model_key` 为会话级模型选择（`<provider>:<model_key>`），`null` 表示 Auto。

**设置会话模型**（2026-10-30 起）：

```http
PUT /agent/api/v1/sessions/{thread_id}/model
Content-Type: application/json
Authorization: Bearer <access_token>

{ "model_key": "deepseek:deepseek-v4-pro" }   // null 表示恢复 Auto
```

```json
{
  "thread_id": "3f0c...",
  "model_key": "deepseek:deepseek-v4-pro",
  "effective": "explicit",
  "model": { "provider": "deepseek", "model_key": "deepseek:deepseek-v4-pro", "display_name": "GPT-4o mini", "capabilities": ["text", "tool_calling"], "context_window": 128000 },
  "updated_at": "2026-10-30T08:00:00Z"
}
```

- 校验顺序固定为「会话归属 → 目录与用户可用性 → 写库」，任一步失败都不写库。
- 幂等：重复提交相同 `model_key` 不修改 `updated_at`、不产生额外副作用，直接返回当前配置。
- `effective` 取值 `explicit` / `auto`；`auto` 时 `model` 为 `null`。
- 错误：会话不存在或非本人 404 `session_not_found`；格式非法 422 `validation_error`；目录不存在或用户无权使用 403 `model_not_available`；控制面不可达 503 `control_plane_unavailable`；`MODEL_RUNTIME__ENABLED=false` 时 503 `model_runtime_disabled`。
- 单次请求覆盖不走此接口，只由 `POST /chat/stream` 的 `model` 字段表达。

**置顶与归档**（2026-11-06 起）：

```http
PUT /agent/api/v1/sessions/{thread_id}/pin
Content-Type: application/json

{ "pinned": true }
```

```http
PUT /agent/api/v1/sessions/{thread_id}/archive
Content-Type: application/json

{ "archived": true }
```

两个接口都返回 `{ "thread_id": "...", "is_pinned": false, "is_archived": true, "updated_at": "..." }`。归档项不出现在默认列表中，通过 `GET /sessions?archived=true` 查询并恢复；置顶只影响排序，归档时保留置顶状态，恢复后继续生效。会话不存在或非本人返回 404 `session_not_found`。

**重命名**：`PATCH /agent/api/v1/sessions/{thread_id}`，body `{ "title": "新标题" }`。标题去首尾空白后 1..80 字符，空白或超长返回 422 `validation_error`；会话不存在或不属于当前用户返回 404 `session_not_found`；成功返回 `{ "thread_id": "...", "title": "新标题" }`。

**删除**：`DELETE /agent/api/v1/sessions/{thread_id}`，成功返回 204 无响应体。同时清理 `session_meta`、`session_messages` 与 checkpointer；checkpointer 删除失败只记 warning，不改变 204。会话不存在返回 404 `session_not_found`；同会话正在生成时返回 409 `lock_not_acquired`。

**历史消息**：

```json
{
  "thread_id": "3f0c...",
  "list": [
    { "role": "user", "content": "帮我查一下天气", "created_at": "2026-10-24T11:59:50Z" },
    { "role": "assistant", "content": "", "tool_calls": [{ "id": "c1", "name": "get_current_time", "args": {} }], "created_at": "2026-10-24T11:59:51Z" },
    { "role": "tool", "name": "get_current_time", "content": "2026-10-24 12:00:00", "created_at": "2026-10-24T11:59:52Z" }
  ],
  "total": 3,
  "page": 1,
  "size": 20,
  "order": "asc"
}
```

- 数据源是 `session_messages` 表，查询条件同时带 `user_id` 与 `thread_id`；没有任何记录时返回 404 `session_not_found`。
- `role` 取值 `user` / `assistant` / `tool` / `system`；`tool_calls` 与 `name` 为可选字段；`created_at` 为落库时间（ISO 8601），用于前端「显示消息时间」。
- `order` 默认 `asc`；传 `desc` 时按 `seq` 倒序返回窗口（供长会话从最新一页向前翻），响应中的 `order` 回显请求值。
- 该接口不读 checkpointer，因此只返回本轮落库后的完整消息。

## 7. SSE 契约（`POST /chat/stream`）

请求：

```http
POST /agent/api/v1/chat/stream
Content-Type: application/json
Accept: text/event-stream
Authorization: Bearer <access_token>
Idempotency-Key: <可选，8~128 字符>
```

```json
{ "message": "你好", "thread_id": "t-demo", "agent_id": "writer" }
```

- `message` 长度 1..4000；`thread_id` 长度 1..64，由前端生成并复用。
- `regenerate` 可选，默认 `false`。为 `true` 时服务端从检查点移除最后一条 AI 回答后重跑模型，并用覆盖写入替换 `session_messages` 中对应序号，不追加重复提问；没有可替换回答时降级为普通回合。
- `resume` 可选，用于恢复一次 HITL 中断：`{ "interrupt_id": "...", "answer": { ... } }`。`interrupt_id` 取自 SSE `interrupt` 事件（1..128），`answer` 按该事件的 `input_schema.fields` 填写。恢复请求复用同一 `thread_id`，服务端从检查点续跑并覆盖写入本轮消息；与 `regenerate=true` 同时出现时返回 **422 `validation_error`**。前提：`HITL__ENABLED=true` 且 `STORAGE__BACKEND=postgres`。
- `agent_id` 可选，请求级选择 Agent Profile（≤32，`^[a-z][a-z0-9_-]{0,31}$`）；省略时使用 `AGENT__DEFAULT_PROFILE`。未配置的 id 返回 **404 `agent_not_found`**，且在建立 SSE 流之前以裸 JSON 返回。Profile 决定系统提示词、工具集与模型参数；`tools: []` 的 Profile 不绑定任何工具。
- `model` 可选，单次覆盖本轮的模型（≤64，`[a-z0-9:_.-]`），取值与 `GET /api/v1/models` 的 `modelKey` 一致；省略或 `null` 表示沿用会话选择 / Profile 默认模型 / Auto，不改变会话默认。仅在 `MODEL_RUNTIME__ENABLED=true` 时生效。
- `reasoning` 可选，`boolean`，缺省 `null`：`true` 表示要求本轮开启思考，服务端按 `model-tasks` 返回的 `capabilities` 校验，缺 `reasoning` 能力位时在流建立前返回 422 `capability_unsupported`；`false` 表示不要求；`null` 沿用模型默认行为。门控必须留在 Agent 侧：网关 `drop_params: true` 会静默丢弃不支持的参数，否则前端无法判断思考是否真的生效。运行时关闭（`MODEL_RUNTIME__ENABLED=false`）时该字段被忽略。
- `preferences` 可省略；省略时行为与旧版完全一致（不追加偏好、注入历史）。字段：`instructions` 可空且 ≤1000、`reply_language` ∈ `auto|zh-CN|en-US`、`response_style` ∈ `concise|balanced|detailed`、`use_history` 布尔（默认 `true`）。
- 偏好由前端从 `GET /api/v1/users/me/preferences` 读出后随请求携带；**不参与鉴权**，服务端只做长度与枚举校验，非法值返回 422 `validation_error` 并带字段级 `details`。
- `use_history=false` 时模型只看到本轮消息（从最后一条 user 消息开始，含其后的工具调用与结果）；本轮消息仍正常写入 checkpointer 与 `session_messages`，历史接口不受影响。
- 每轮都会显式下发偏好字段，未携带时服务端按默认值处理，避免同一 `thread_id` 沿用上一轮的 `use_history=false`。
- 响应头：`Content-Type: text/event-stream; charset=utf-8`、`Cache-Control: no-cache`、`X-Accel-Buffering: no`。
- 编码由 sse-starlette 的 `EventSourceResponse` 完成，分隔符统一 LF；前端按 `\n\n` 切帧。

帧格式（实测输出，见 `agent-service/tests/test_chat_stream.py`；`schema_version` 由编码层统一注入）：

```text
id: 1
event: citations
data: {"citations": [{"source_id": "kb-1", "title": "示例文档", "snippet": "示例片段", "score": 0.9}], "schema_version": "1"}

id: 2
event: token
data: {"text": "你好", "schema_version": "1"}

id: 3
event: tool_call
data: {"name": "get_current_time", "args": {"timezone": "UTC"}, "schema_version": "1"}

id: 4
event: tool_result
data: {"name": "get_current_time", "preview": "2026-10-24 12:00:00", "schema_version": "1"}

id: 5
event: token
data: {"text": "现在是 12 点", "schema_version": "1"}

id: 6
event: done
data: {"thread_id": "t-demo", "message_id": "t-demo:1", "schema_version": "1"}

```

思考内容（仅当模型返回 `reasoning_content` 时出现，位于首个 `token` 之前）：

```text
id: 1
event: reasoning
data: {"text": "先分析问题再回答", "schema_version": "1"}
```

HITL 中断（仅 `HITL__ENABLED=true` 且触发澄清或兼容性确认时出现；本轮不再发送 `done`）：

```text
id: 7
event: interrupt
data: {"interrupt_id": "int-1", "interaction_type": "clarify_requirements", "question": "还缺预算和使用场景，请补充后继续。", "input_schema": {"fields": [{"name": "budget_yuan", "label": "预算（元）", "type": "number", "required": true, "min": 1000}, {"name": "scenario", "label": "主要用途", "type": "select", "required": false, "options": [{"value": "GAMING", "label": "游戏"}]}], "submit_label": "提交并继续"}, "context": {"missing_slots": ["budget_yuan"]}, "schema_version": "1"}
```

| event | data | 说明 |
| --- | --- | --- |
| `token` | `{ "text": "...", "schema_version": "1" }` | 增量文本，前端按序拼接 |
| `reasoning` | `{ "text": "...", "schema_version": "1" }` | 增量思考内容；由 LiteLLM 归一化 `reasoning_content` 后下发，与 `token` 严格分离。仅部分模型提供，前端必须容忍该事件缺失；不得并入正文、不得写入历史消息 |
| `tool_call` | `{ "name": "...", "args": {}, "schema_version": "1" }` | 模型发起工具调用 |
| `tool_result` | `{ "name": "...", "preview": "...", "schema_version": "1" }` | 工具结果摘要，`preview` 截断到 200 字符 |
| `citations` | `{ "citations": [{ "source_id": "...", "title": "...", "snippet": "...", "score": 0.9 }], "schema_version": "1" }` | 可选：仅 `RAG__ENABLED=true` 且检索到结果时发送，位于首个 `token` 之前；`score` 可省略 |
| `interrupt` | `{ "interrupt_id": "...", "interaction_type": "clarify_requirements \| confirm_compatibility", "question": "...", "input_schema": { "fields": [...], "submit_label": "..." }, "context": {}, "schema_version": "1" }` | HITL 暂停：本轮以 `interrupt` 结束，前端进入等待输入状态并用 `resume` 续跑；不会随后发送 `done`。字段 `type` ∈ `number\|select\|radio\|text` |
| `done` | `{ "thread_id": "...", "message_id": "...", "schema_version": "1", "build_result": { ... } }` | 正常结束；`thread_id` 是客户端原始值，不含用户命名空间。`message_id` 为本轮助手消息的稳定标识（`{thread_id}:{seq}`），缺失时前端隐藏反馈入口；`build_result` 可选，仅 PC 配置求解成功时出现 |
| `error` | `{ "code": "...", "message": "...", "schema_version": "1" }` | 流内错误；此时 HTTP 状态码已是 200 |

`build_result` 结构（snake_case，前端容忍字段缺失）：

| 字段 | 说明 |
| --- | --- |
| `build_id` | 配置快照 ID |
| `components[]` | 8 类硬件，含 `category`、`model_name`、`brand`、`title`、`platform`、`seller`、`price_source`、`spec_summary`、`price_fen`、`purchase_url`、`benchmark`、`offer_verified_at` |
| `total_price_fen` / `budget_max_fen` / `budget_status` | 总价、预算上限与预算校验结论；均为整数分 |
| `compatibility[]` / `overall_status` | 兼容性明细与总状态，取值为 `PASS`/`WARNING`/`FAIL`/`UNKNOWN` |
| `demo_offer_count` | 演示价（`price_source=MOCK_DEMO`）条数；大于 0 时前端必须常驻展示「演示价格，非真实在售」 |
| `reason_summary` | 选型理由摘要；正文的权威来源仍是 `token` 事件 |

`components[].price_source` 决定价格提示等级，逐件来源优先于聚合计数：

- `MOCK_DEMO`：演示占位价，禁止表述为已核验报价；对应 `demo_offer_count`。
- `PLATFORM_OBSERVED`：电商平台检索到的参考价，商品真实在售但未经人工核验；前端展示「参考价（平台观测，未经人工核验）」，不能与演示价混用文案。
- `OWNER_VERIFIED`：人工核验价。

注意：Java 落库响应中的 `demo_offer_count` 统计「非 `OWNER_VERIFIED`」条数，平台观测价也会被计入，不能据此判定演示价；SSE 投影按 `MOCK_DEMO` 重新计算。

版本化约定（WP2.3）：

- `schema_version` 当前为 `"1"`，由 `agent-service/app/api/v1/sse.py` 统一注入，路由不各自拼装。
- 新增字段一律可选；旧前端忽略后仍能正常渲染（前端 `stream-chat.spec.ts` 有对应兼容测试）。
- 事件类型增删、必填字段变更或语义改变时必须提升版本号，并同步前端类型、管理端类型与本文。
- 契约基线是 `agent-service/tests/contracts/sse_events.json`；`pytest` 比对字段集合与版本号，改动必须显式提交进快照。

语义约束（已验证）：

- `id` 从 1 递增，仅业务事件编号，心跳注释不带 `id`。
- 心跳由 sse-starlette 生成，形如 `: ping - 2026-10-28T15:32:35+00:00`；客户端必须忽略所有以 `:` 开头的行。频率由 `AGENT__SSE_HEARTBEAT_SECONDS` 控制。
- `done` 之前先写 `session_messages`，因此前端收到 `done` 立即查历史即可看到本轮消息；写入失败只记 warning，不改变流结果。
- 客户端断开时服务端取消图执行并释放锁，避免无效模型调用与计费。
- 未识别事件必须忽略，保证新增事件类型时旧前端仍可用。
- `citations` 只在 `RAG__ENABLED=true` 且检索到结果时出现；检索按 `user_id` / `roles` 在检索前过滤，检索异常降级为「无引用」，不影响 `token`/`done` 流程。引用片段只进入本轮提示词，不写历史；前端按 `sourceId` 去重后以折叠面板附在当前助手消息正文之后，刷新页面即消失。

流建立前的错误走 HTTP + JSON：

| HTTP | code | 场景 |
| --- | --- | --- |
| 401 | `unauthorized` / `token_expired` / `token_invalid` | 鉴权失败 |
| 409 | `duplicate_request` | 相同 `Idempotency-Key` 已完成 |
| 409 | `request_in_progress` | 相同 `Idempotency-Key` 处理中 |
| 409 | `lock_not_acquired` | 等待窗口内未拿到会话锁 |
| 409 | `hitl_unavailable` | 携带 `resume` 但 `HITL__ENABLED=false` 或存储不是 `postgres` |
| 409 | `interrupt_not_found` | 该 `thread_id` 没有待恢复的中断 |
| 409 | `interrupt_mismatch` | `interrupt_id` 与当前待恢复中断不一致（如已回答或已被新回合覆盖） |
| 409 | `interrupt_expired` | 中断距 checkpoint 创建已超过 `HITL__INTERRUPT_TTL_SECONDS` |
| 422 | `validation_error` | 字段校验失败，带 `details` |
| 429 | `quota_exceeded` | 今日请求额度用尽（Java 在 `model-tasks` 中原子扣减），响应体带 `quota` |
| 403 | `model_not_available` | 模型不存在或当前用户不可用 |
| 422 | `capability_unsupported` | 当前模型不支持所需能力 |
| 503 | `control_plane_unavailable` / `upstream_error` | 控制面不可达（平台模型会显式降级，仅 BYOK 失败）或上游返回未知错误 |
| 503 | `credential_unavailable` | BYOK 任务缺少可用凭证，无法装配模型 |
| 503 / 422 | `llm_not_configured` / `llm_provider_unsupported` | 模型未配置（503）或 Provider 无法映射到网关前缀（422） |

额度超限响应（裸 JSON，HTTP 429，流建立前返回）：

```json
{
  "code": "quota_exceeded",
  "message": "今日请求额度已用尽，请明日再试",
  "request_id": "...",
  "quota": {
    "quota_type": "daily_requests",
    "limit": 100,
    "used": 100,
    "reset_at": "2026-10-31T00:00:00Z"
  }
}
```

- `quota` 由 Java 的 `data` 透传而来（Java 使用 camelCase，Agent 转成 snake_case）；字段缺失时不输出。
- 控制面不可达时，Auto / Managed 请求记 `warning` 并显式降级到进程默认模型，SSE 正常结束；BYOK 请求不降级，返回 503。
- 流已开始后只能发 `error` 事件，不得修改 HTTP 状态码。

流内错误码：`request_timeout`（整轮超时）、`agent_error`（图执行异常）、`hitl_resume_invalid`（恢复内容缺少必填字段或取值非法，用户可补充后重试）。

### 7.1 Assistant 内容中的 OpenUI 块（可选能力）

生成式 UI 不新增 SSE 事件，而是 `token` 拼接完成后的文本内容约定。双端开关默认关闭：Agent 侧 `OPENUI__ENABLED`（Compose 由宿主 `OPENUI_ENABLED` 注入）控制是否注入契约，前端 `VITE_OPENUI_ENABLED` 控制是否解析；两端必须同步开启。

- 仅识别 info string 为 `openui` 的 Markdown 围栏块（反引号或波浪线），块外内容继续按 Markdown 渲染。
- 块内为 openui-lang DSL，首行必须是 `root = ...`；围栏外出现 DSL 不视为 UI。
- Agent 契约由 `frontend/scripts/generate-openui-prompt.mjs` 生成，禁止手改；CI `openui:prompt:check` 检查漂移。
- 前端只渲染已闭合块；流式中的未闭合尾块展示占位，终态仍未闭合时降级为原文。
- 规模上限：单条消息最多 8 块，单块 20000 字符 / 400 行 / 括号嵌套 32 层；超限块整块按原文代码块展示。Agent 侧 `OPENUI__MAX_BLOCKS`（1..10，默认 4）只写入提示词，不保证模型遵守。
- Action 白名单仅 `continue_conversation`、`open_url`；不接受 JavaScript、任意函数或业务 API，`open_url` 仅允许 http/https。
- 历史消息与实时消息共用同一解析逻辑；历史渲染不自动执行任何 Action。
- 表单状态只存前端 `sessionStorage`：键为 `openui-state:v1:<threadId>:<contentHash>`，记录带 `version`，上限 100 条；不写服务端、URL 或 Cookie。
- 解析失败、未注册组件、非法 Props、单块异常均由前端隔离并降级，不影响同条消息的 Markdown 与其他块。

## 8. 错误码总表

**Java 数字码**（`shared/error/CommonErrorCode.java`）：

| 区间 | 示例 | 含义 |
| --- | --- | --- |
| `0` | `0` | 成功 |
| `1xxxx` | `10001` 参数不合法、`10005` 方法不支持、`10007` 登录失败限流（**已实现，单实例**） | 通用请求错误 |
| `2xxxx` | `20001` 未认证、`20002` 无权限（含 `/api/v1/admin/**` 的 `ADMIN` 规则） | 认证与权限 |
| `3xxxx` | `30001` 资源不存在、`30002` 状态冲突（含「删除当前设备」） | 资源与通用业务 |
| `4xxxx` | `40102` 当前口令不正确、`40103` 新旧口令相同、`40104` 邮箱已被占用、`40105` 会话不存在或不属于当前用户；模型模块 `402xx`：`40201` 额度用尽（429）、`40202` 模型不可用、`40203` 能力不支持、`40204` 运行时未启用、`40205` 服务身份校验失败、`40206` 任务不存在、`40207` 用户令牌无效、`40208` 模型标识格式不正确、`40209` BYOK 未启用（404）、`40210` 连接不存在或不属于当前用户（404）、`40211` Provider 不受支持（400）、`40212` 连接已存在（409）、`40213` 凭证损坏（500）、`40214` 接入地址非法（400）、`40215` 凭证已兑换（409）、`40216` 凭证已撤销（401）、`40217` 凭证验证失败/上游不可用（502）、`40218` 非 BYOK 任务无需兑换（409）、`40219` Provider 拒绝凭证（422）、`40221` 定价版本重复（409） | 业务模块 |
| `5xxxx` | `50000` 系统错误、`50001` 依赖不可用 | 服务端 |

**Agent 字符串码**（下表为主要对外码；完整清单与控制面透传码以 `agent-service/app/core/error_codes.py` 注册表为唯一来源，`tests/test_error_codes.py` 扫描源码字面量，未登记即测试失败）：

| code | HTTP | 含义 |
| --- | --- | --- |
| `unauthorized` / `token_expired` / `token_invalid` | 401 | 鉴权 |
| `forbidden` | 403 | 开发令牌接口在非开发环境被调用 |
| `session_not_found` | 404 | 会话无消息或不属于当前用户 |
| `duplicate_request` / `request_in_progress` / `lock_not_acquired` | 409 | 幂等与并发 |
| `hitl_unavailable` / `interrupt_not_found` / `interrupt_mismatch` / `interrupt_expired` | 409 | HITL 恢复校验：未启用或存储不支持 / 无待恢复中断 / 中断 ID 不匹配 / 中断已过期 |
| `hitl_resume_invalid` | 422（流内以 `error` 事件下发） | 恢复内容缺失必填字段或取值非法 |
| `validation_error` | 422 | 请求校验 |
| `input_rejected` | 422 | 输入侧护栏命中：超长、控制字符、零宽字符或高置信度提示词注入（指标 `agent_input_guard_violations_total{rule}`）；请求在建流前被拒绝，不占用会话锁与限流配额 |
| `rate_limited` | 429 | 对话限流：每用户固定窗口内请求数超限（默认 20 次/分钟），响应头带 `Retry-After`（秒）；指标 `agent_rate_limit_rejections_total{scope}` |
| `invalid_pagination` | 400 | 分页参数越界（`page < 1`、`size` 不在 1..100） |
| `redis_unavailable` | 503 | Redis 已配置但不可用 |
| `llm_not_configured` / `llm_provider_unsupported` | 503 | 模型不可用 |
| `quota_exceeded` | 429 | 模型运行时每日请求额度用尽（响应体附 `quota`） |
| `model_not_available` | 403 | 模型不存在或当前用户不可用 |
| `capability_unsupported` | 422 | 当前模型不支持所需能力 |
| `credential_revoked` | 401 | BYOK 凭证已撤销，下一次请求必须重新配置 |
| `credential_lease_consumed` / `lease_not_byok` | 409 | 凭证已兑换需重新发起 / 非 BYOK 任务无需兑换 |
| `credential_rejected` | 422 | Provider 拒绝了该 BYOK 凭证 |
| `credential_unavailable` | 503 | BYOK 任务缺少可用凭证 |
| `control_plane_unavailable` / `upstream_error` | 503 | Java 控制面不可达 / 上游未知错误 |
| `metrics_disabled` | 404 | 指标端点关闭 |
| `metrics_forbidden` | 403 | 指标端点已配置 `METRICS__TOKEN`，请求未带或带错 `X-Metrics-Token` |
| `http_{status}` | 原始状态 | 框架级 404/405 |
| `internal_error` | 500 | 未捕获异常 |
| `request_timeout` / `agent_error` | 流内 | SSE `error` 事件 |

两套码不可混用：前端按调用目标选择解析方式；日志与告警也分域统计。

## 9. 跨端对照结论

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| 前端对话路径与 Agent 路由 | 一致：前端 `/chat/stream` + `/agent` 前缀 = Agent `/api/v1/chat/stream` | `frontend/src/features/sessions/api/stream-chat.ts`、`agent-service/app/api/v1/chat.py` |
| 会话与消息路径 | 一致：`/sessions`、`/sessions/{id}/messages` | `frontend/src/features/sessions/api/sessions.ts`、`agent-service/app/api/v1/sessions.py` |
| 登录字段与 `tokenType` | 一致：Java 返回 `accessToken` + `tokenType=Bearer` + `user`，前端按 Bearer 拼接 | `AuthService.java`、`frontend/src/features/auth/api/auth.ts` |
| 用户身份传递 | 一致：Token 由前端携带；Agent 用 `sub`（公开 UUID）做命名空间 | `agent-service/app/core/security.py`、`frontend/src/features/auth/model/auth-session.ts` |
| 历史消息字段 | 一致：`message_id/role/content/tool_calls/name/created_at` 与前端 `SessionMessage` 对齐；`message_id` 缺失时前端退回会话下标 key 并隐藏反馈入口 | `session_store/mapping.py`、`frontend/src/features/sessions/api/types.ts` |
| SSE 事件与结束语义 | 一致：8 类事件，正常回合以 `done` 收尾、HITL 回合以 `interrupt` 收尾；`done.message_id` 为本轮助手消息标识，缺失时前端忽略；未知事件忽略 | 第 7 节 |
| 消息反馈 | 一致：前端 `PUT/DELETE /api/v1/messages/{messageId}/feedback`、`GET /api/v1/feedback` 与 Java `MessageFeedbackController` 同名同形；管理端用 `/api/v1/admin/feedback*` | 第 5.8 节、`frontend/src/features/feedback/api/feedback.ts`、`admin/src/features/feedback/api/admin-feedback-api.ts` |
| 输入护栏与限流 | 一致：Agent 在建流前返回 422 `input_rejected` / 429 `rate_limited`（带 `Retry-After`）；前端把 `ApiError.message` 直接展示在助手气泡，未做按码分支，新增码不会破坏渲染 | 第 7、8 节、`agent-service/app/services/{input_guard,rate_limit}.py` |
| 心跳 | 一致：服务端 `: ping - ...`，前端跳过 `:` 开头行 | `frontend/src/core/http/sseStream.ts` |
| 响应信封 | 有意差异：Java 信封 / Agent 裸 JSON，前端分别封装 | 第 3 节 |
| 错误码 | 有意差异：数字 / 字符串，HTTP 状态语义一致 | 第 8 节 |
| 分页上限 | 一致：默认 20、上限 100、越界统一 400 | `PageQuery.java`、`sessions.py` |
| 指标端点 | 一致：Nginx 白名单为主、应用内 `METRICS__TOKEN` 兜底 | 两份 nginx 模板、`health.py` |
| 超时 | 分层：Nginx `/agent/` 3600s、`/api/` 60s；Agent 另有整轮 `request_timeout_seconds`；前端用 `AbortSignal` | nginx 模板、`chat.py` |
| Java → Agent 调用 | **已确认不做**：前端经 Nginx 直连 Agent，Java 无 Agent 客户端 | `architecture-overview.md` §3 |
| Agent → Java 内部接口 | 已实现：Agent 内网直连 `/internal/v1/**`（服务令牌 `token_use=service`，用户态调用额外带 `X-User-Token`） | 本文 §5.6、`agent-service/app/services/control_plane*.py` |
| 幂等 | Agent 对话接口支持 `Idempotency-Key`（Redis，Redis 未启用时降级）；Java 内部 `/internal/v1/model-tasks` 支持任务级幂等（键由 Agent 按「用户+会话+客户端键」派生），冲突返回 409 `40220` | `chat.py`、`model_resolver.py`、`ModelRuntimeService.java` |

## 10. 版本与演进

- 兼容性变更（新增可选字段、新增事件类型、新增端点）可直接在当前版本发布；前端必须忽略未知事件与未知字段。SSE 事件的版本号与判定规则见 §7「版本化约定」。
- 破坏性变更（删字段、改语义、改错误码、改路径）必须新增 `/api/v2`，并在两端并行一段时间。
- Agent 新增路由必须挂在 `API_PREFIX`（`/api/v1`）下，否则 Nginx 转发后路径不匹配。
- 变更后必须同步：前端类型与 API 模块、Java DTO、Agent Pydantic Schema、本文与相关服务文档、`.env.example`（涉及变量时）。完整流程见 [development-rules.md](development-rules.md)。

## 11. 待确认事项

| 编号 | 内容 | 影响 |
| --- | --- | --- |
| A-01 | ~~是否补齐 Java → Agent 服务间调用~~ → **已关闭（2026-10-28）**：保持前端直连 Agent，不新增服务间契约 | 无 |
| A-02 | ~~Agent 历史消息默认 `size` 是否统一为 50~~ → **已关闭（2026-10-28）**：三端默认值统一为 20；当时前端按场景显式取 50 / 100，**2026-11-01 复核已改为会话 20 / 历史 100**（§4） | 无 |
| A-03 | ~~`metrics` 端点是否加鉴权或网关白名单~~ → **已关闭（2026-10-28）**：Nginx 白名单为主，`METRICS__TOKEN` 为应用内兜底 | 无 |
| A-04 | ~~分页超限的状态码是否统一（400 vs 422）~~ → **已关闭（2026-10-28）**：Agent 显式校验并返回 400 `invalid_pagination` | 无 |

## 12. 接口文档入口与机器可读契约

### 12.1 手写权威文档（当前唯一阅读入口）

| 文档 | 覆盖范围 |
| --- | --- |
| 本文 | 跨端路径、鉴权、信封、分页、SSE、错误码、内部接口摘要 |
| `docs/services/application-service/api-reference.md` | Java 全部 14 个 Controller 的端点签名、DTO 字段、校验与错误码；§8 内部接口 |
| `docs/services/agent-service/api-reference.md` | Agent 11 条路由（10 个业务操作 + `/health` 别名）、SSE 事件、错误码 |

### 12.2 机器可读 OpenAPI（已验证事实，2026-11-01）

| 端 | 接入方式 | 路径 | 生效范围 |
| --- | --- | --- | --- |
| Java | `springdoc-openapi-starter-webmvc-ui:3.1.1` + `shared/config/OpenApiConfig.java` | `/v3/api-docs`、`/swagger-ui.html` | 默认 profile 与 `dev` 启用；**`prod` 禁用**（`application-prod.yaml`） |
| Agent | FastAPI 内置，`app/main.py` 按 `APP_ENV` 控制 | `/docs`、`/openapi.json`（另 `/redoc`） | 默认 `dev` / `staging` 开启；**`APP_ENV=prod` 关闭**（`docs_url` / `redoc_url` / `openapi_url` 置 `None`） |

访问口径：

- Java 的 OpenAPI 与 Swagger UI **经 Nginx 不可达**：网关只转发 `/api/`，无 `/v3/api-docs` 或 `/swagger-ui` 的 location，请求会落到静态回退；仅在直连 `127.0.0.1:8080` 时可用。
- Agent 的 `/docs` 与 `/openapi.json` **经 Nginx 可达**（`/agent/` 剥前缀），即 `/agent/docs`、`/agent/openapi.json`；生产容器 `APP_ENV=prod` 时这三个路径返回 404。

两端策略已对齐（2026-11-01 修复）：生产均不暴露 OpenAPI 与交互文档，本地与联调环境保留。

【未实现】尚未把 OpenAPI JSON 导出并纳入版本控制，也没有「OpenAPI ↔ 手写 api-reference ↔ 代码」的三方一致性校验脚本。

