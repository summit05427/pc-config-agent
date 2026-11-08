# Java 业务端接口参考

| 项 | 内容 |
| --- | --- |
| 状态 | 全部验证：认证、用户、模型、内部与管理端端点均已对照代码复核 |
| 基线 | `main`（2026-11-02 复核） |
| 最后核验 | 2026-11-02 |
| 主要证据 | `identity/web/{Auth,UserProfile,UserPassword,UserSession,UserPreference,AdminUser,AdminAuditLog}Controller.java`、`identity/application/{AdminUserService,AdminAuditLogService}.java`、`identity/infrastructure/{MyBatisUserDirectory,MyBatisAuthAuditQuery}.java`、`model/web/{Model,AdminModelCatalog,AdminModelUsage,AdminModelConnection}*Controller.java`、`model/application/{AdminModelCatalog,AdminModelUsage,AdminModelConnection}Service.java`、`model/infrastructure/{AdminModelCatalog,AdminModelUsage,AdminModelConnection}Mapper.*`、`model/web/dto/*`、`shared/api/*`、`shared/error/*`、`shared/security/TokenUseFilter.java`、`shared/web/GlobalExceptionHandler.java` |

## 1. 适用范围

只列**当前已实现**的接口。管理端接口（`/api/v1/admin/**`，需 `ADMIN`）已实现，见 §9；角色限制统一由 `SecurityConfig` 处理，Controller 内不重复判权。

Base path：公开接口为 `/api/v1`（Nginx 侧对外仍是 `/api/`，前缀由网关决定）；内部接口为 `/internal/v1`，不经 Nginx 暴露，见 §8。

## 2. 通用约定

### 2.1 请求标识

- 请求头 `X-Request-Id` 可选。合法值（字母、数字、`.`、`_`、`-`，长度 ≤64）会被复用；其余情况服务端生成 32 位 UUID。
- 响应头必定回写 `X-Request-Id`，响应体 `requestId` 与之一致。

### 2.2 成功信封

```json
{
  "code": 0,
  "message": "ok",
  "data": { },
  "requestId": "3f7c1c0d9b4a4c0f8e2a1b7d6c5e4f30"
}
```

`code` 为业务码，成功固定 `0`；HTTP 状态码表达协议语义。

### 2.3 失败信封

```json
{
  "code": 20001,
  "message": "未登录或登录状态已失效",
  "requestId": "3f7c1c0d9b4a4c0f8e2a1b7d6c5e4f30"
}
```

`data` 为空时不出现在 JSON 中（`@JsonInclude(NON_NULL)`）。对外不输出堆栈、SQL、类名与服务器路径。

业务失败时信封**顶层**还会输出 `errorType`（小写蛇形，如 `quota_exceeded`），仅错误响应出现、不放进 `data`；完整规则见根 `docs/api-contract.md` §2，`errorType` 取自错误码枚举的 `errorType()` 实现（`shared/error/ErrorCode.java`）。

### 2.4 参数校验失败

HTTP 400，`code=10001`，`data` 为字段错误列表：

```json
{
  "code": 10001,
  "message": "请求参数不合法",
  "data": [
    { "field": "username", "message": "username 不能为空" }
  ],
  "requestId": "..."
}
```

## 3. 接口清单

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| `POST` | `/api/v1/auth/login` | 否 | 账号密码登录，签发访问令牌并下发刷新 Cookie |
| `POST` | `/api/v1/auth/refresh` | 否（凭 Cookie） | 轮换刷新令牌并换发访问令牌 |
| `POST` | `/api/v1/auth/logout` | 否（凭 Cookie） | 撤销当前刷新会话并清除 Cookie |
| `GET` | `/api/v1/auth/me` | 是 | 当前登录用户与角色 |
| `GET` | `/api/v1/users/me/profile` | 是 | 读取本人资料（展示名 / 邮箱 / 简介） |
| `PUT` | `/api/v1/users/me/profile` | 是 | 全量更新本人资料，返回更新后的完整资料 |
| `PUT` | `/api/v1/users/me/password` | 是 | 修改本人密码，并撤销其他设备的刷新会话 |
| `POST` | `/api/v1/auth/logout-all` | 是 | 撤销本人全部刷新会话（退出所有设备）并清除 Cookie |
| `GET` | `/api/v1/users/me/sessions` | 是 | 分页查询登录设备，按刷新令牌族聚合 |
| `DELETE` | `/api/v1/users/me/sessions/{familyId}` | 是 | 撤销指定设备的刷新会话 |
| `GET` | `/api/v1/users/me/preferences` | 是 | 读取本人 Agent 偏好；未保存时返回默认值 |
| `PUT` | `/api/v1/users/me/preferences` | 是 | 全量保存本人 Agent 偏好，返回最新值 |
| `GET` | `/api/v1/models` | 是 | 可用模型目录（平台模型 + 用户 BYOK），字段见根 `docs/api-contract.md` §5.2 |
| `GET` | `/api/v1/model-connections` | 是 | 本人 BYOK 连接列表，只返回凭证掩码 |
| `POST` | `/api/v1/model-connections` | 是 | 创建连接并加密保存 API Key |
| `POST` | `/api/v1/model-connections/{connectionId}/verify` | 是 | 真实远程验证：探测 Provider 并写入 `lastVerifiedAt` |
| `DELETE` | `/api/v1/model-connections/{connectionId}` | 是 | 删除连接并撤销其凭证 |
| `GET` | `/api/v2/models` | 是 | 模型目录分页（`list/total/page/size`），v1 全量数组保持兼容 |
| `GET` | `/api/v2/model-connections` | 是 | 本人模型连接分页，字段同 §7.1 |
| `GET` | `/api/v1/users/me/model-usage` | 是 | 本人当日额度快照与使用明细分页，支持自然日过滤 |
| `GET` | `/api/v1/admin/users` | 是（`ADMIN`） | 管理端用户分页：`keyword` 模糊匹配登录名/邮箱、`status` 过滤 |
| `PATCH` | `/api/v1/admin/users/{publicId}/status` | 是（`ADMIN`） | 启用/禁用用户；禁用会撤销其全部刷新会话 |
| `PATCH` | `/api/v1/admin/users/{publicId}/roles` | 是（`ADMIN`） | 更新角色（仅 `USER` / `ADMIN`），保证至少保留一个启用管理员 |
| `GET` | `/api/v1/admin/audit-logs` | 是（`ADMIN`） | 认证审计分页，支持 `event` / `username` 过滤 |
| `GET` | `/api/v1/admin/models` | 是（`ADMIN`） | 模型目录分页（含停用），支持关键字、Provider 与启用状态过滤 |
| `PATCH` | `/api/v1/admin/models/{provider}/{modelKey}/status` | 是（`ADMIN`） | 启用/停用模型；停用只影响后续调用解析 |
| `GET` | `/api/v1/admin/models/{provider}/{modelKey}/pricing` | 是（`ADMIN`） | 定价版本分页，按生效时间倒序 |
| `POST` | `/api/v1/admin/models/{provider}/{modelKey}/pricing` | 是（`ADMIN`） | 追加定价版本；同一生效时间冲突返回 409 |
| `GET` | `/api/v1/admin/model-providers` | 是（`ADMIN`） | Provider 目录（含停用）与模型数量统计，不分页 |
| `PATCH` | `/api/v1/admin/model-providers/{code}/status` | 是（`ADMIN`） | 启用/停用 Provider；停用后其下模型不可用 |
| `GET` | `/api/v1/admin/model-usage` | 是（`ADMIN`） | 全量用量明细分页，支持用户、Provider、模型、凭证来源、成本状态、结果与日期过滤，按 `occurredAt` 升/降序 |
| `GET` | `/api/v1/admin/model-usage/summary` | 是（`ADMIN`） | 用量聚合：总量、成本状态分布、Provider / 模型 Top 20；多币种不求和 |
| `GET` | `/api/v1/admin/model-connections` | 是（`ADMIN`） | 用户模型连接只读分页，支持用户、Provider、状态过滤；只返回凭证掩码与状态 |
| `GET` | `/v3/api-docs` | 否 | OpenAPI JSON（prod 关闭） |
| `GET` | `/swagger-ui.html` | 否 | Swagger UI（prod 关闭） |
| `GET` | `/actuator/health`、`/actuator/info` | 否 | 健康与信息端点 |

## 4. 认证接口（login / refresh / logout / logout-all）

### 4.1 POST /api/v1/auth/login

请求：

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `username` | string | 是 | `@NotBlank` |
| `password` | string | 是 | `@NotBlank` |

```json
{ "username": "admin", "password": "******" }
```

成功 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "accessToken": "eyJhbGciOiJSUzI1NiJ9....",
    "tokenType": "Bearer",
    "expiresIn": 600,
    "user": { "publicId": "3f0c1c0d-...", "username": "admin", "roles": ["ADMIN"] }
  },
  "requestId": "..."
}
```

响应头同时下发刷新 Cookie：

```http
Set-Cookie: agent_refresh=<43 字符随机串>; Path=/api/v1/auth; Max-Age=2592000; Secure; HttpOnly; SameSite=Strict
```

- `expiresIn` 单位为秒，取自 `JWT_ACCESS_TTL`（默认 `10m`）。
- 响应体**永不含**刷新令牌；`data.token` 字段已随双令牌改造删除。
- 登录响应直接带用户信息，前端登录后无需再请求 `/auth/me`。
- `publicId` 与令牌 `sub` 一致；内部自增主键不出现在任何响应。

失败：

| 场景 | HTTP | code |
| --- | --- | --- |
| 账号或口令错误 | 401 | 20001 |
| 字段为空 | 400 | 10001 |

### 4.2 POST /api/v1/auth/refresh

无请求体，凭 Cookie `agent_refresh` 换取新令牌。

请求头：

| 头 | 必填 | 说明 |
| --- | --- | --- |
| `Cookie` | 是 | `agent_refresh=<刷新令牌>`，浏览器自动携带 |
| `Origin`（缺失时退回 `Referer`） | 是 | 必须命中 `CORS_ALLOWED_ORIGINS` 或与 `Host` 同源，否则 403 `20002` |

成功 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": { "accessToken": "eyJhbGciOiJSUzI1NiJ9....", "tokenType": "Bearer", "expiresIn": 600 },
  "requestId": "..."
}
```

响应头 `Set-Cookie` 下发**新的**刷新令牌；旧令牌被标记 `rotated`，`replaced_by_id` 指向新会话。

失败：

| 场景 | HTTP | code |
| --- | --- | --- |
| Cookie 缺失 / 令牌未知 / 已撤销 / 闲置或绝对过期 / 用户被禁用 | 401 | 20001 |
| 宽限期内重复出示已轮换的旧令牌 | 401 | 20001 |
| 超宽限期重放旧令牌（整族撤销，`revoked_reason=replay`） | 401 | 20001 |
| 来源不可信 | 403 | 20002 |

### 4.3 POST /api/v1/auth/logout

无请求体，凭 Cookie 撤销当前刷新会话。

- 成功 200，`data` 为空；响应头 `Set-Cookie` 置 `Max-Age=0` 清除 Cookie。
- 幂等：无 Cookie、Cookie 已失效或已撤销时同样返回 200 `code=0`。
- 同样受 Origin 校验保护，来源不可信返回 403 `20002`。
- 只撤销当前设备；撤销全部设备见 `4.4`。

### 4.4 POST /api/v1/auth/logout-all

请求头：`Authorization: Bearer <token>`；无请求体。

- 成功 200，`data` 为空；响应头 `Set-Cookie` 置 `Max-Age=0` 清除 Cookie。
- 撤销该用户全部仍然有效的刷新会话（`revoked_reason=logout`），所有设备下一次刷新均 401。
- 依赖访问令牌而不是 Cookie，因此 Cookie 已失效也能成功；撤销本身幂等，重复调用不报错。
- 不做 Origin 校验：跨站请求无法携带 `Authorization` 头，且刷新 Cookie 是 `SameSite=Strict`。
- 失败：未带 Token / 非法 / 过期返回 401 `20001`；令牌有效但用户已删除返回 401 `20001`。

### 4.5 认证审计

- 登录成功、登录失败、超宽限期的刷新重放、退出、退出全部设备、修改口令，以及刷新时发现用户已被禁用，均写入 `auth_audit_logs`。
- 记录字段：`username`、`ip`（`X-Forwarded-For` 首段 → `X-Real-IP` → `remoteAddr`）、`user_agent`（≤255）、`request_id`；不含口令、Token、Cookie 与请求体。
- 写入使用独立事务（`REQUIRES_NEW`），认证失败这类最终抛异常的流程也能留痕；审计写入失败只记一条 `warning`，不影响登录、退出或改密的结果。
- `role_changed` 由管理端角色变更接口写入；审计查询见 §9.4（需 `ADMIN`）。

## 5. GET /api/v1/auth/me

请求头：`Authorization: Bearer <token>`。

成功 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": { "publicId": "3f0c1c0d-...", "username": "admin", "roles": ["ADMIN"] },
  "requestId": "..."
}
```

`roles` 已去掉 `ROLE_` 前缀，且只透出业务角色（框架认证因子如 `FACTOR_BEARER` 被过滤）。`publicId` 是 `users.public_id`，同时是令牌 `sub`；前端在刷新页面后用它恢复用户信息。

失败：

| 场景 | HTTP | code |
| --- | --- | --- |
| 未带 Token / Token 非法 / 过期 / issuer 或 audience 不符 | 401 | 20001 |

## 6. 账户接口（profile / sessions / preferences）

路径固定为 `me`，不提供 `/users/{id}`：用户只能读写自己的资料、设备与偏好，不存在按 ID 越权的入口。认证用 `Authorization: Bearer <token>`，令牌 `sub` 即 `users.public_id`。

### 6.1 GET /api/v1/users/me/profile

成功 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "publicId": "3f0c1c0d-...",
    "username": "admin",
    "displayName": "运营管理员",
    "email": "admin@example.com",
    "bio": "负责后台运营",
    "roles": ["ADMIN"],
    "status": "ACTIVE",
    "createdAt": "2026-10-29T08:00:00Z",
    "updatedAt": "2026-10-29T09:00:00Z"
  },
  "requestId": "..."
}
```

`displayName` / `email` / `bio` 未设置时为 `null`，不是空串；响应不含内部自增主键与口令摘要。

### 6.2 PUT /api/v1/users/me/profile

请求体为全量提交，`displayName` 必填：

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `displayName` | string | 是 | 去首尾空白后 1..64，不可为纯空白 |
| `email` | string \| null | 否 | 邮箱格式，≤255；空串或纯空白按「未设置」存 `NULL` |
| `bio` | string \| null | 否 | ≤500；空串按「未设置」存 `NULL` |

```json
{ "displayName": "运营管理员", "email": "admin@example.com", "bio": "负责后台运营" }
```

成功响应与 6.1 相同（更新后的最新值）；`updated_at` 由服务端在 SQL 中写入 `now()`，因为该表没有更新触发器。登录名与角色不可通过本接口修改。

失败：

| 场景 | HTTP | code |
| --- | --- | --- |
| 未带 Token / 非法 / 过期 | 401 | 20001 |
| `displayName` 空白或超长、邮箱格式错误 | 400 | 10001 |
| 邮箱已被其他账号占用 | 409 | 40104 |
| 令牌有效但用户已被删除 | 401 | 20001 |

空串归一化为 `NULL` 的原因：`users.email` 有唯一约束，多个空串会互相冲突，而 `NULL` 不参与唯一比较。

### 6.3 PUT /api/v1/users/me/password

请求体：

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `currentPassword` | string | 是 | 非空白，≤128；与库内 BCrypt 摘要比对，不 trim |
| `newPassword` | string | 是 | 8..64，且不得与当前口令相同 |

```json
{ "currentPassword": "old-password", "newPassword": "new-password" }
```

成功 200，无 `data`。改密与撤销其他设备在同一事务内完成：

```sql
UPDATE refresh_sessions
SET revoked_at = now(), revoked_reason = 'password_change'
WHERE user_id = ?
  AND family_id <> 当前 Access Token 的 sid
  AND revoked_at IS NULL
```

- 当前设备靠访问令牌的 `sid` claim（= `refresh_sessions.family_id`）识别；刷新 Cookie 的 `Path=/api/v1/auth`，本接口收不到，不能作为判据。
- 其他设备下一次刷新即 401，需要重新登录；当前设备的刷新 Cookie 仍可正常轮换。
- 日志只记录用户名与撤销会话数，不记录口令、摘要或令牌。

失败：

| 场景 | HTTP | code |
| --- | --- | --- |
| 未带 Token / 非法 / 过期 | 401 | 20001 |
| 令牌缺少 `sid`（改造前签发的存量令牌，最长 10 分钟过期） | 401 | 20001 |
| 当前口令不正确 | 400 | 40102 |
| 新口令与当前口令相同 | 400 | 40103 |
| 新口令长度不在 8..64、当前口令为空白或超过 128 | 400 | 10001 |
| 令牌有效但用户已被删除 | 401 | 20001 |

口令类失败一律用 400 而不是 401：前端把 401 解释为登录失效，会触发单飞刷新与全局登出，改密失败不应让用户掉线。

### 6.4 GET /api/v1/users/me/sessions

请求头：`Authorization: Bearer <token>`；查询参数 `page`、`size`（默认 1 / 20，`size` 上限 100）。

响应 `data`：

```json
{
  "list": [
    {
      "familyId": "0b7c5a7e-1f4d-4c2f-9a55-5d0b2f8c7a11",
      "createdAt": "2026-10-29T02:00:00Z",
      "lastUsedAt": "2026-10-29T02:10:00Z",
      "idleExpiresAt": "2026-11-05T02:10:00Z",
      "absoluteExpiresAt": "2026-11-28T02:00:00Z",
      "current": true
    }
  ],
  "total": 1,
  "page": 1,
  "size": 20
}
```

聚合规则与 SQL 一致：

```sql
SELECT family_id,
       min(created_at)  AS created_at,
       max(last_used_at) AS last_used_at,
       min(idle_expires_at) FILTER (WHERE revoked_at IS NULL AND idle_expires_at > now()) AS idle_expires_at,
       min(absolute_expires_at) FILTER (WHERE revoked_at IS NULL AND absolute_expires_at > now()) AS absolute_expires_at
FROM refresh_sessions
WHERE user_id = ?
GROUP BY family_id
HAVING count(*) FILTER (WHERE revoked_at IS NULL AND idle_expires_at > now() AND absolute_expires_at > now()) > 0
ORDER BY coalesce(max(last_used_at), min(created_at)) DESC
LIMIT ? OFFSET ?
```

- 同一次登录的整条轮换链只算一台设备；`last_used_at` 取全链最大值，轮换过的族也能看到最近活跃时间。
- 族内已无有效行（整族被撤销或已过期）时整族不出现，`total` 口径与 `list` 一致。
- `current` 由访问令牌 `sid` 与 `family_id` 比对得出，**只用于展示**；令牌缺少 `sid` 时全部为 `false`。
- 不返回刷新令牌摘要、内部主键与 IP/UA（当前未采集）。

### 6.5 DELETE /api/v1/users/me/sessions/{familyId}

请求头：`Authorization: Bearer <token>`；无请求体。成功 200，无 `data`，只撤销该族中仍然有效的行（`revoked_reason=logout`）。

失败：

| 场景 | HTTP | code |
| --- | --- | --- |
| `familyId` 不是合法 UUID | 400 | 10001 |
| 目标是当前设备（`sid` 与之相同） | 409 | 30002 |
| 族不存在、已撤销或属于其他用户 | 404 | 40105 |
| 未带 Token / 非法 / 过期 | 401 | 20001 |

- 归属校验下推到 SQL：`WHERE user_id = ? AND family_id = ?::uuid AND revoked_at IS NULL`，返回 0 行即视为不存在，避免「先查再删」的竞态。
- 当前设备必须走 `/auth/logout`：撤销后需要同步清除浏览器 Cookie，本接口拿不到 Cookie 的写入通道。
- 已撤销的族再次删除返回 404：设备列表里已经看不到它，前端按「已被移除」处理即可。

### 6.6 GET /api/v1/users/me/preferences

请求头：`Authorization: Bearer <token>`；无请求体。

响应 `data`：

```json
{
  "instructions": "回答尽量简短",
  "replyLanguage": "zh-CN",
  "responseStyle": "concise",
  "useHistory": true,
  "updatedAt": "2026-10-29T09:00:00Z"
}
```

- 从未保存过偏好时返回默认值：`instructions = null`、`replyLanguage = auto`、`responseStyle = balanced`、`useHistory = true`、`updatedAt = null`（不伪造保存时间）。
- 偏好是「客户端声明的用户偏好」，不参与鉴权，也不写入令牌；对话时由前端随 `POST /agent/api/v1/chat/stream` 的 `preferences` 传给 Agent。
- 令牌有效但用户已被删除时（Access Token 余窗最长 10 分钟，见安全文档 §9）同样返回默认值，不泄露任何数据；写入则返回 401。

### 6.7 PUT /api/v1/users/me/preferences

请求体为全量提交，四个字段都必填：

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `instructions` | string \| null | 否 | ≤1000；去首尾空白，空串或纯空白按「未设置」存 `NULL` |
| `replyLanguage` | string | 是 | `auto` / `zh-CN` / `en-US` |
| `responseStyle` | string | 是 | `concise` / `balanced` / `detailed` |
| `useHistory` | boolean | 是 | 是否把历史消息注入对话上下文 |

```json
{ "instructions": "回答尽量简短", "replyLanguage": "zh-CN", "responseStyle": "concise", "useHistory": true }
```

成功响应与 6.6 相同；`updated_at` 由 SQL 显式写 `now()`（`user_preferences` 没有更新触发器）。

失败：

| 场景 | HTTP | code |
| --- | --- | --- |
| 未带 Token / 非法 / 过期 | 401 | 20001 |
| 枚举取值非法、`useHistory` 缺失、`instructions` 超长 | 400 | 10001 |
| 令牌有效但用户已被删除 | 401 | 20001 |

枚举校验刻意用 `@Pattern` 而不是 Java 枚举字段：非法取值走 Bean Validation，返回 `10001` 且 `data` 为字段级 `details`；若直接反序列化成枚举，会退化成 `10004` 并丢失字段名。

写入 SQL（`UserPreferenceMapper.upsert`）：

```sql
INSERT INTO user_preferences (user_id, instructions, reply_language, response_style, use_history, updated_at)
SELECT u.id, ?, ?, ?, ?, now()
FROM users u
WHERE u.public_id = ?::uuid
ON CONFLICT (user_id) DO UPDATE
SET instructions   = EXCLUDED.instructions,
    reply_language = EXCLUDED.reply_language,
    response_style = EXCLUDED.response_style,
    use_history    = EXCLUDED.use_history,
    updated_at     = EXCLUDED.updated_at
```

`SELECT ... FROM users` 直接解析内部主键：用户不存在时插入 0 行，服务层据此返回 401，避免「先查用户再写」的额外往返。

## 7. 模型连接、凭证与用量（BYOK 与运营，PR4/PR5/PR6 已实现）

统一约定：

- 四个连接与凭证接口受 `BYOK_ENABLED` 控制：未开启时均返回 404 `40209`，不泄露除「未启用」以外的细节；用量查询只受运行时总开关控制。
- 归属校验下推到 SQL：连接不属于当前用户时统一返回 404 `40210`，不区分「不存在」与「无权限」。
- 任何响应都不含明文密钥或密文，只返回 `credentialId`、`maskedHint`、`status`、`createdAt`；不提供回读接口。
- 凭证以 AES-256-GCM 加密存储，密文格式 `v1:<key_version>:<base64(nonce|tag|ciphertext)>`；主密钥只注入 Java，缺失时启动即失败（`app.model.credential` 的 `@AssertTrue` 守卫）。
- 密钥轮换通过 `MODEL_CRED_MASTER_KEYS`（`<version>:<base64>`，英文逗号分隔）配置多版本密钥环；解密时按密文里的 `key_version` 选密钥，旧密文继续可用。密钥环非法或缺少当前 `MODEL_CRED_KEY_VERSION` 时启动失败。
- 完整字段与跨端契约见根 `docs/api-contract.md` §5.3。

响应对象（四个接口共用，`data` 为单个对象或 `{ list }`）：

```json
{
  "id": "…",
  "provider": "deepseek",
  "providerName": "DeepSeek",
  "baseUrl": "https://api.deepseek.com/v1",
  "status": "ACTIVE",
  "lastVerifiedAt": null,
  "createdAt": "2026-10-30T08:00:00Z",
  "credential": {
    "id": "…",
    "maskedHint": "sk-****abcd",
    "status": "UNVERIFIED",
    "createdAt": "2026-10-30T08:00:00Z"
  }
}
```

### 7.1 GET /api/v1/model-connections

返回当前用户未删除的连接，按创建时间倒序；`data.list` 永不为 `null`。

### 7.2 POST /api/v1/model-connections

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `providerCode` | string | 是 | 去空白后 ≤32，必须存在于 Provider 目录且已启用 |
| `baseUrl` | string | 否 | ≤255；仅 `http` / `https` 且必须带 host；留空用 Provider 默认地址 |
| `apiKey` | string | 是 | 8..512，提交后即加密，明文不落库、不回显 |

- 同一用户同一 Provider 已有 `ACTIVE` 连接时返回 409 `40212`。
- Provider 不存在或未启用返回 400 `40211`；`baseUrl` 协议或主机不合法返回 400 `40214`。
- 成功返回 HTTP 200 + `code=0` 与创建结果，凭证状态为 `UNVERIFIED`。

### 7.3 POST /api/v1/model-connections/{connectionId}/verify

本地校验密文完整性后调用 Provider 做真实探测（PR5）：优先 `GET {baseUrl}/models`；Provider 不支持该方法（404/405/501）时退化为 `max_tokens=1` 的最小 chat 请求。成功写 `last_verified_at` 并把凭证置为 `VERIFIED`；上游拒绝写入拒绝态，超时或网络失败按不可用处理，不把临时故障写成永久失败。

- 连接不存在或不属于当前用户：404 `40210`。
- 密文损坏或主密钥不匹配：500 `40213`。
- Provider 拒绝凭证：422 `40219`；验证时上游不可达或未返回可用结果：502 `40217`。

### 7.4 DELETE /api/v1/model-connections/{connectionId}

连接软删为 `DELETED`，其凭证同步置 `REVOKED`，此后不可再被使用；成功返回 HTTP 200 + `code=0`，`data` 为空。连接不存在或不属于当前用户：404 `40210`。

### 7.5 POST /internal/v1/model-tasks/{taskId}/credential-lease（PR5）

仅服务令牌可调用，不要求 `X-User-Token`。任务必须未过期、未撤销且为 BYOK；成功后用条件 UPDATE（`leased_at IS NULL`）标记已兑换，并返回 `{ credentialType, secret, expiresIn }`。明文只出现在本次响应中，不落库、不写日志。

- 任务不存在、过期或已撤销：404 `40206`。
- 任务已兑换：409 `40215`；非 BYOK 任务：409 `40218`。
- 凭证已撤销：401 `40216`；凭证被 Provider 拒绝：422 `40219`；上游不可用：502 `40217`。

### 7.6 POST /internal/v1/model-tasks（任务创建，幂等）

仅服务令牌可调用，用户身份由 `X-User-Token` 提供；Agent 以此创建模型运行时任务并按任务扣减每日额度。

| 请求头 | 必填 | 约束 |
| --- | --- | --- |
| `Idempotency-Key` | 否 | 1..64，字符集 `[A-Za-z0-9._:-]`；由 Agent 按「用户 + 会话 + 客户端键」做 SHA-256 派生 |

- 同 `(用户, Idempotency-Key)` 重放直接返回原任务，不重复扣额度；容量不足导致的并发抢占由部分唯一索引 `uk_model_runtime_tasks_idem` 兜底，插入冲突后同事务回读既有任务。
- 同键但 `threadId` / `model` 与已有任务不一致，或原任务已过期（超过 `MODEL_TASK_TTL`）：409 `40220`。
- 幂等窗口等于任务 TTL，默认 10 分钟；过期任务由 `ModelRuntimeTaskCleanupJob` 置为 `EXPIRED`，不物理删除（用量明细外键仍引用任务行）。
- 先插入任务再扣额度：额度不足时抛出异常并整体回滚，任务不会残留。

### 7.7 GET /api/v1/users/me/model-usage（PR6）

用户身份只取令牌 `sub`，归属条件下推到 SQL；不提供按用户 ID 查询的入口。

请求参数：

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `page` | int | 否 | ≥1，默认 1 |
| `size` | int | 否 | 1..100，默认 20 |
| `from` | date | 否 | `YYYY-MM-DD`，UTC 自然日，含当天 |
| `to` | date | 否 | `YYYY-MM-DD`，UTC 自然日，含当天 |

响应 `data`：

```json
{
  "quota": { "quotaType": "daily_requests", "limit": 100, "used": 3, "resetAt": "2026-11-01T00:00:00Z" },
  "list": [
    {
      "invocationId": "…",
      "taskId": "…",
      "threadId": "t-demo",
      "modelRole": "conversation",
      "provider": "deepseek",
      "modelKey": "deepseek:deepseek-v4-pro",
      "credentialSource": "MANAGED",
      "promptTokens": 120,
      "completionTokens": 30,
      "latencyMs": 850,
      "status": "success",
      "errorType": null,
      "costStatus": "ESTIMATED",
      "costBearer": "PLATFORM",
      "currency": "USD",
      "estimatedCost": 0.000036,
      "occurredAt": "2026-10-30T08:00:00Z"
    }
  ],
  "total": 5, "page": 1, "size": 20
}
```

- 额度快照取 UTC 当日；当日没有额度行时 `used=0`、`limit` 取 `MODEL_QUOTA_DAILY_REQUESTS`、`resetAt` 为次日 00:00Z。
- 明细按 `occurredAt` 倒序；`from` / `to` 转成 `[from 00:00Z, to+1 00:00Z)` 半开区间。
- `page < 1`、`size` 越界、`from > to` 返回 400 `10001`；运行时未启用返回 404 `40204`。
- `promptTokens` / `completionTokens` / `latencyMs` 上游未提供时为 `null`，不填 0。
- 成本由 Java 依据 `model_pricing` 在入库时定格：`costStatus=ESTIMATED` 时金额与 `currency` 非空；`UNKNOWN`（缺定价或 token 用量）与 `BYOK_NOT_BILLED`（用户自带凭证）金额为 `null`；`costBearer` 为 `PLATFORM` / `USER`。Agent 上报不再包含 `estimatedCost`。

### 7.8 定时对账（PR6）

`ModelUsageReconciliationJob` 按 `MODEL_RECONCILE_CRON`（UTC，默认 `0 5 0 * * *`）只读统计前一 UTC 自然日的额度溢出、归属不一致、额度用满、负数费用与成本状态不一致（`ESTIMATED` 必须有金额与币种，其他状态必须没有金额）；`MODEL_RECONCILE_ENABLED=false` 时跳过。日志只输出计数，不输出用户标识。手工执行 `scripts/reconcile-model-usage.ps1`（默认 `-DaysBack 1`），严重项退出码 1。

### 7.9 GET /api/v2/models 与 /api/v2/model-connections（分页）

v1 的 `/api/v1/models`、`/api/v1/model-connections` 继续返回全量数组，仅供旧客户端兼容与回滚；前端已于 2026-11-01 切到 v2。v2 只提供分页读取，不重复创建、验证与删除入口。

| 方法 | 路径 | 查询参数 | 响应（`data`） |
| --- | --- | --- | --- |
| `GET` | `/api/v2/models` | `page`、`size` | `{ list, total, page, size }`，条目字段同 §5.2 |
| `GET` | `/api/v2/model-connections` | `page`、`size` | `{ list, total, page, size }`，条目字段同 §7.1，按创建时间倒序 |

- 分页参数由 `PageQuery` 校验，非法返回 400 `10001`；页码超出总数返回空 `list` 与真实 `total`。
- 两个端点都要求访问令牌；分页 SQL 在数据库侧执行，不做内存截断。
- 运行时未启用返回 404 `40204`；BYOK 未启用返回 404 `40209`，与 v1 一致。

## 8. 内部接口（Agent → Java）

仅供 Agent 在容器网络内调用，路径不在 `/api/v1` 下、不经 Nginx 暴露。跨端契约摘要见根 [`docs/api-contract.md`](../../api-contract.md) §5.2；本节只补本服务侧实现细节，不重复整表。

### 8.1 鉴权模型

| 环节 | 本服务实现 |
| --- | --- |
| 服务令牌签发 | `POST /internal/v1/auth/service-token` 用**表单** `client_id` + `client_secret`（不是 JSON，避免被前端误调用，也避免凭据进 URL 查询串）；`SecurityConfig` 对该路径放行；`ServiceTokenService` 复用现有 RS256 密钥与 issuer / audience 签发 |
| 服务令牌内容 | `token_use=service`、`sub=clientId`、`scope=[model-runtime:read, model-usage:write]`，TTL 取 `INTERNAL_AUTH_TOKEN_TTL`（默认 5m）；凭据比较用 `MessageDigest.isEqual` 定长比较 |
| 令牌用途隔离 | `TokenUseFilter`：`/internal/v1/**` 只接受 `token_use=service`，`/api/v1/**` 只接受 `token_use=access`；不匹配返回 401 `20001` |
| scope 授权 | `/internal/v1/model-usage` 需要 `SCOPE_model-usage:write`；其余 `/internal/v1/**` 需要 `SCOPE_model-runtime:read`；无权限 403 `20002` |
| 用户身份透传 | 创建/读取任务与模型可用性校验额外要求 `X-User-Token`；`UserTokenValidator` 验签后要求 `token_use=access` 且 `sub` 是 UUID（即 `users.public_id`），失败 401 `40207`；**不接受请求体中的用户字段** |
| 凭证兑换例外 | `POST /internal/v1/model-tasks/{taskId}/credential-lease` 只认服务令牌，不要求 `X-User-Token`（任务创建时已校验过用户） |
| 开关 | `MODEL_RUNTIME_ENABLED=false` 时运行时相关内部接口返回 404 `40204`；BYOK 相关错误码见 §7 |

### 8.2 端点与字段

| 方法 | 路径 | 鉴权 | 请求 | 响应（`data`） |
| --- | --- | --- | --- | --- |
| `POST` | `/internal/v1/auth/service-token` | 放行（凭 client 凭据） | 表单 `client_id`、`client_secret`，均 `@NotBlank` | `{ "accessToken": "...", "tokenType": "Bearer", "expiresIn": 300 }` |
| `POST` | `/internal/v1/model-tasks` | 服务令牌 + `X-User-Token`；可选 `Idempotency-Key` | `{ "threadId": "...", "model": "deepseek:deepseek-v4-pro" }`；`threadId` 必填 ≤128，`model` 可空 ≤64 | `{ "taskId": "...", "provider": "deepseek", "modelKey": "...", "credentialSource": "MANAGED\|BYOK", "credentialId": "...", "baseUrl": "...", "expiresAt": "...", "capabilities": ["text", "reasoning", "reasoning_visible"] }`；`credentialId` / `baseUrl` 仅 BYOK 有值；`capabilities` 供 Agent 做请求侧能力门控，取值为开放字符串数组 |
| `GET` | `/internal/v1/model-tasks/{taskId}` | 服务令牌 + `X-User-Token` | 路径 `taskId` 为 UUID | 同任务结构；能力位按 `modelKey` 回查目录，模型随后下架时返回空数组（任务本身仍有效） |
| `POST` | `/internal/v1/model-tasks/{taskId}/credential-lease` | 仅服务令牌 | 路径 `taskId` 为 UUID | `{ "credentialType": "api_key", "secret": "sk-...", "expiresIn": 300 }`；明文只出现一次 |
| `POST` | `/internal/v1/model-access/check` | 服务令牌 + `X-User-Token` | `{ "modelKey": "deepseek:deepseek-v4-pro" }`，必填 ≤64 | `{ "available": true, "provider": "...", "modelKey": "...", "displayName": "...", "capabilities": ["text","tool_calling"], "contextWindow": 128000 }` |
| `POST` | `/internal/v1/model-usage` | 服务令牌（`model-usage:write`） | `{ "records": [ ... ] }`，单批 1..20 条 | `{ "accepted": 1, "duplicated": 0, "rejected": 0 }` |

单条用量记录字段（`UsageRecordRequest`）：`invocationId`（UUID）、`taskId`（UUID）、`modelRole`（≤32）、`provider`（≤32）、`modelKey`（≤64）、`credentialSource`（≤16）、`promptTokens` / `completionTokens` / `latencyMs`（可空、非负）、`status`（`success` / `failure`）、`errorType`（可空 ≤64）、`occurredAt`（必填）。费用不在上报中传递，由 Java 按 `model_pricing` 计算。

### 8.3 行为与错误

- **幂等键**：`Idempotency-Key` 可缺省；空白视为未提供，格式必须是 `[A-Za-z0-9._:-]{1,64}`，否则 400 `10001`。同 `(用户, 键)` 重放返回原任务且不重复扣额度；同键但 `threadId` / `model` 不同或原任务已过期返回 409 `40220`。并发重放由部分唯一索引 `uk_model_runtime_tasks_idem` 兜底，插入冲突后同事务回读既有任务。
- **额度**：任务创建时按 UTC 自然日扣减每日请求额度，额度用尽返回 429 `40201`，`data` 带额度详情；创建任务与扣额度在同一事务内，失败整体回滚。
- **任务读取**：任务不存在、已过期或已撤销返回 404 `40206`。
- **模型可用性**：模型不存在或当前账号不可用返回 403 `40202`；`modelKey` 格式错误返回 400 `40208`。
- **凭证兑换**：任务过期或撤销 404 `40206`；已兑换 409 `40215`；非 BYOK 任务 409 `40218`；凭证已撤销 401 `40216`；Provider 拒绝 422 `40219`；上游不可用 502 `40217`。
- **用量上报**：同一 `invocationId` 重复上报计入 `duplicated` 不重复入库；批次超过 20 条返回 400 `10001`。

### 8.4 PC 配置内部接口（2026-11-08 新增）

字段级契约以根 [`docs/api-contract.md`](../../api-contract.md) §5.7 为准，本表只列实现入口与鉴权差异。

| 方法 | 路径 | 鉴权 | 实现要点 |
| --- | --- | --- | --- |
| `GET` | `/internal/v1/pc/hardware/candidates` | 服务令牌 | 可选 `category`；响应 `catalogVersion` / `total` / `list[]`，硬件字段含 `hardwareId`、`category`、`brand`、`modelName`、`displayName`、`specifications`、`specSummary`、三个状态位 |
| `GET` | `/internal/v1/pc/hardware/{hardwareId}` | 服务令牌 | 单硬件详情；不存在 404 `40301` |
| `GET` | `/internal/v1/pc/benchmarks` | 服务令牌 | 可选 `hardwareId` / `category`；无数据返回空列表，不猜分 |
| `GET` | `/internal/v1/pc/offers` | 服务令牌 | 可选 `hardwareId` / `category` / `verifiedOnly`；响应含 `dataStatus`、`priceUnit=CNY_FEN`、`verifiedOfferCount`、`mockOfferCount` |
| `POST` | `/internal/v1/pc/builds/solve` | 服务令牌 + `X-User-Token` | 请求 `budgetMaxFen` / `scenario` / `minMemoryGb` / `minStorageGb` / `requireVerifiedOffers`；成功写快照，无解返回 `solved=false` 与结构化 `failure` |
| `POST` | `/internal/v1/pc/builds/validate` | 服务令牌 | 请求固定八个类别字段；缺类别 400 `40303`；只校验不落库 |
| `GET` | `/internal/v1/pc/builds/{buildId}` | 服务令牌 + `X-User-Token` | 按 `build_id + user_id` 查询，归属判断下推到 SQL；不存在或他人 404 `40302` |

- 错误码：`40301` 硬件不存在、`40302` 快照不存在或非本人、`40303` 配置不完整、`40304` 需求非法、`40305` 目录不可用、`40306` 用户令牌无效。
- 金额一律人民币整数分；`priceSource=OWNER_VERIFIED` 表示人工核验价，`MOCK_DEMO` 表示演示占位价，**不得表述为已核验**。
- scope 复用 `model-runtime:read`（服务令牌默认携带）；实现细节见 [docs/pc-config/api-contract.md](../../pc-config/api-contract.md)。

## 9. 管理端接口（已实现）

> **已验证（2026-11-01）**：`AdminUserController` / `AdminAuditLogController` 与 `AdminUserService` / `AdminAuditLogService` 已落地；用户查询与更新走 `UserDirectory`，审计查询走新增的 `AuthAuditQuery` 端口（`MyBatisAuthAuditQuery`）。V18 补充 `users(created_at)`、`users(status, created_at)` 与 `auth_audit_logs(event, created_at)` 索引。接口测试见 `AdminUserApiTests`、`AdminAuditLogApiTests`；模型目录与定价见 §9.5。

统一约定：

- 路径前缀 `/api/v1/admin/**` 由 `SecurityConfig` 统一限制为 `ADMIN` 角色；Controller 内不重复判权。
- 未认证/令牌失效返回 401 `20001`，非 `ADMIN` 返回 403 `20002`；响应使用 Java 统一信封。
- 审计表 `auth_audit_logs` 只记录事件与定位信息，不记录口令、Token、Cookie。

### 9.1 GET /api/v1/admin/users

请求参数：

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `page` | int | 否 | ≥1，默认 1 |
| `size` | int | 否 | 1..100，默认 20 |
| `keyword` | string | 否 | 登录名/邮箱模糊匹配；去空白后 ≤64 |
| `status` | string | 否 | `ACTIVE` / `DISABLED` |

响应 `data`：

```json
{
  "list": [
    {
      "publicId": "3f0c1c0d-...",
      "username": "demo",
      "email": "demo@example.com",
      "roles": ["USER"],
      "status": "ACTIVE",
      "createdAt": "2026-10-30T08:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 20
}
```

条目只含公开 ID、登录名、邮箱、角色、状态与创建时间，不含内部主键与口令摘要。

### 9.2 PATCH /api/v1/admin/users/{publicId}/status

请求体：

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `status` | string | 是 | `ACTIVE` / `DISABLED`，`@NotBlank` + `@Pattern` |

成功返回更新后的用户摘要（字段同 9.1）。行为：

- 禁用时同时撤销该用户全部刷新会话（`revoked_reason=user_disabled`），在线会话下一次刷新即 401；已签发 Access Token 仍在最长 10 分钟余窗内有效（见安全文档 §9）。
- 不能禁用当前登录的管理员自己，返回 409 `30002`。
- 启用只更新状态，不自动恢复已撤销的刷新会话。

失败：

| 场景 | HTTP | code |
| --- | --- | --- |
| `publicId` 非 UUID、`status` 非法 | 400 | 10001 |
| 目标用户不存在 | 404 | 30001 |
| 禁用自己 | 409 | 30002 |
| 未认证 / 非 ADMIN | 401 / 403 | 20001 / 20002 |

### 9.3 PATCH /api/v1/admin/users/{publicId}/roles

请求体：

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `roles` | string[] | 是 | 非空、≤10 个元素；元素只能为 `USER` / `ADMIN`；去空白并去重 |

成功返回更新后的用户摘要（字段同 9.1）。约束：

- 角色白名单仅 `USER` / `ADMIN`，客户端不能传自定义角色。
- 变更后系统必须仍有至少一个启用状态的 `ADMIN`；若目标当前是启用 ADMIN 且新角色不含 `ADMIN`，且当前启用管理员数 ≤1，返回 409 `30002`。
- 角色未变化时不写库、不记审计。

失败：

| 场景 | HTTP | code |
| --- | --- | --- |
| `publicId` 非 UUID、`roles` 为空/超长/含非法角色 | 400 | 10001 |
| 目标用户不存在 | 404 | 30001 |
| 变更后无启用管理员 | 409 | 30002 |
| 未认证 / 非 ADMIN | 401 / 403 | 20001 / 20002 |

### 9.4 GET /api/v1/admin/audit-logs

请求参数：

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `page` | int | 否 | ≥1，默认 1 |
| `size` | int | 否 | 1..100，默认 20 |
| `event` | string | 否 | 8 类事件白名单：`login_success` / `login_failure` / `refresh_replay` / `logout` / `logout_all` / `password_change` / `user_disabled` / `role_changed` |
| `username` | string | 否 | 精确匹配；去空白后 ≤64 |

响应 `data`：

```json
{
  "list": [
    { "event": "login_success", "username": "admin", "ip": "203.0.113.10", "createdAt": "2026-10-30T08:00:00Z" }
  ],
  "total": 1,
  "page": 1,
  "size": 20
}
```

条目只含事件、登录名、IP 与发生时间；不含 User-Agent、请求 ID、口令、Token 与 Cookie。`ip` 可能为空。

失败：

| 场景 | HTTP | code |
| --- | --- | --- |
| 分页越界、`event` 不在白名单、`username` 超长 | 400 | 10001 |
| 未认证 / 非 ADMIN | 401 / 403 | 20001 / 20002 |

### 9.5 模型目录与定价（D-05）

> **已验证（2026-11-01）**：`AdminModelCatalogController` / `AdminModelCatalogService` / `AdminModelCatalogMapper` 已落地，单测 `AdminModelCatalogServiceTests` 13 条通过（Docker 无关）。跨端摘要见根 `docs/api-contract.md` §5.1。

设计约束：

- 目录条目**只能启停、不可删除**：历史用量台账以 `provider + modelKey` 引用目录，删除会破坏追溯。
- 定价**只追加版本**，不修改既有记录；用量成本在入库时按当时生效版本定格，调价不回算历史台账。
- 模型列表的最新定价用 `SELECT DISTINCT ON (provider, model_key) ... ORDER BY effective_from DESC` 一次批量取回，避免逐模型查询（N+1）。

#### 9.5.1 GET /api/v1/admin/models

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `page` | int | 否 | ≥1，默认 1 |
| `size` | int | 否 | 1..100，默认 20 |
| `keyword` | string | 否 | 展示名或模型标识模糊匹配（`ILIKE`）；≤64，空串=不过滤 |
| `provider` | string | 否 | Provider 代码精确匹配；≤32，空串=不过滤 |
| `enabled` | string | 否 | `true` / `false`，空串=不过滤；其他取值 400 `10001` |

响应 `data`：

```json
{
  "list": [
    {
      "provider": "deepseek",
      "modelKey": "deepseek-v4-pro",
      "displayName": "GPT-4o mini",
      "contextWindow": 128000,
      "capabilities": ["text", "tool_calling"],
      "capabilitySource": "MANUAL",
      "verifiedAt": null,
      "enabled": true,
      "providerEnabled": true,
      "latestPricing": {
        "id": 3,
        "currency": "USD",
        "inputPricePerMillion": 0.15,
        "outputPricePerMillion": 0.6,
        "effectiveFrom": "2026-11-01T00:00:00Z",
        "createdAt": "2026-11-01T02:00:00Z"
      }
    }
  ],
  "total": 3, "page": 1, "size": 20
}
```

- 按 `provider, modelKey` 升序；含停用条目与停用 Provider。
- `providerEnabled=false` 表示 Provider 已停用，其下模型即使 `enabled=true` 也不可用。
- `latestPricing` 取 `effectiveFrom` 最新一条，无定价为 `null`。
- 能力元数据解析失败时降级为空数组并记 `warn`，不因单条脏数据整体失败。

#### 9.5.2 PATCH /api/v1/admin/models/{provider}/{modelKey}/status

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `enabled` | boolean | 是 | `@NotNull` |

成功后返回更新后的模型摘要（字段同 9.5.1）。状态未变化时幂等，不写库、不产生变更日志。

#### 9.5.3 GET /api/v1/admin/models/{provider}/{modelKey}/pricing

查询参数 `page` / `size`（同分页约定）。响应按 `effectiveFrom DESC, id DESC` 排序：

```json
{
  "list": [
    { "id": 3, "currency": "USD", "inputPricePerMillion": 0.15, "outputPricePerMillion": 0.6,
      "effectiveFrom": "2026-11-01T00:00:00Z", "createdAt": "2026-11-01T02:00:00Z" }
  ],
  "total": 1, "page": 1, "size": 20
}
```

#### 9.5.4 POST /api/v1/admin/models/{provider}/{modelKey}/pricing

请求体：

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `currency` | string | 否 | `^[A-Za-z]{3}$`；缺省按 `USD`，写入前统一转大写 |
| `inputPricePerMillion` | number | 是 | ≥0，最多 12 位整数与 6 位小数（每百万输入 token 单价） |
| `outputPricePerMillion` | number | 是 | ≥0，同上（每百万输出 token 单价） |
| `effectiveFrom` | string | 是 | ISO-8601 瞬时时间，服务端按 UTC 存储 |

- 先查 `(provider, modelKey, effectiveFrom)` 是否已存在，冲突返回 409 `40221`；并发插入由表上唯一约束兜底，`DuplicateKeyException` 同样转 409。
- 写入后回读失败抛 `IllegalStateException`（500），避免返回不存在的版本。
- 成功返回新增版本（结构同 9.5.3 条目）。

失败：

| 场景 | HTTP | code |
| --- | --- | --- |
| `provider` / `modelKey` 格式非法、单价为负或精度超限、`effectiveFrom` 缺失 | 400 | 10001 |
| 模型不存在 | 404 | 30001 |
| 同一生效时间已存在定价版本 | 409 | 40221 |
| 未认证 / 非 ADMIN | 401 / 403 | 20001 / 20002 |

#### 9.5.5 GET /api/v1/admin/model-providers

Provider 是受控的小基数目录，返回全量列表不分页，按 `code` 升序：

```json
[
  { "code": "deepseek", "displayName": "DeepSeek", "protocol": "openai-compatible",
    "defaultBaseUrl": null, "enabled": true, "modelCount": 3, "enabledModelCount": 2 }
]
```

`modelCount` / `enabledModelCount` 由单条 SQL 的相关子查询统计，不按 Provider 逐条查库。

#### 9.5.6 PATCH /api/v1/admin/model-providers/{code}/status

请求体同 9.5.2（`enabled` 必填）。成功后返回更新后的 Provider 摘要（字段同 9.5.5）。停用 Provider 后其下模型即使启用也不可用；操作幂等。

### 9.6 管理端用量与模型连接只读（2026-11-02 已实现）

> 实现：`model/web/AdminModelUsageController.java`、`model/web/AdminModelConnectionController.java`、`model/application/AdminModelUsageService.java`、`model/application/AdminModelConnectionService.java`；单测 `AdminModelUsageServiceTests`（7 条）、`AdminModelConnectionServiceTests`（4 条）共 11 条通过（Docker 无关）。迁移 `V19__add_admin_query_indexes.sql` 补充时间与组合索引。

#### 9.6.1 GET /api/v1/admin/model-usage

| 参数 | 类型 / 约束 | 说明 |
| --- | --- | --- |
| `page` / `size` | 默认 1 / 20，`size ≤ 100` | 服务端分页 |
| `userId` | UUID，≤36 | 非 UUID 返回 400 `10001` |
| `provider` / `modelKey` | ≤32 / ≤64 | 精确匹配 |
| `credentialSource` | `MANAGED` / `BYOK` | 空串不过滤 |
| `costStatus` | `ESTIMATED` / `UNKNOWN` / `BYOK_NOT_BILLED` | 空串不过滤 |
| `status` | `success` / `failure` | 调用结果 |
| `from` / `to` | `YYYY-MM-DD` | **UTC 自然日**闭区间；`to` 转次日零点开区间；`from > to` 返回 400 `10001` |
| `order` | `asc` / `desc`（默认 `desc`） | 只能按 `occurredAt` 排序，禁止指定列名 |

响应 `data` 为 `{list,total,page,size}`，条目字段见 §5.1 契约；`username` 取 `COALESCE(NULLIF(display_name,''), username)`，不返回内部自增主键、对话内容或凭证信息。

#### 9.6.2 GET /api/v1/admin/model-usage/summary

只接受 `provider`、`modelKey`、`credentialSource`、`from`、`to`；**刻意不支持** `userId` / `costStatus` / `status`，保证卡片总量与明细筛选口径可解释。响应结构：

```json
{
  "from": null,
  "to": null,
  "totals": { "requestCount": 1, "successCount": 1, "failureCount": 0,
    "promptTokens": 120, "completionTokens": 80, "totalTokens": 200,
    "estimatedCost": 0.0001, "currency": "USD",
    "estimatedCount": 1, "unknownCostCount": 0, "byokNotBilledCount": 0 },
  "byCostStatus": [{ "costStatus": "ESTIMATED", "requestCount": 1, "estimatedCost": 0.0001, "currency": "USD" }],
  "byProvider": [{ "provider": "deepseek", "requestCount": 1, "promptTokens": 120,
    "completionTokens": 80, "totalTokens": 200, "estimatedCost": 0.0001, "currency": "USD" }],
  "byModel": [{ "provider": "deepseek", "modelKey": "deepseek-v4-pro", "requestCount": 1,
    "promptTokens": 120, "completionTokens": 80, "totalTokens": 200,
    "estimatedCost": 0.0001, "currency": "USD" }]
}
```

- 聚合以 4 条 SQL 完成（totals / byCostStatus / byProvider / byModel），不逐组查库。
- **多币种不求和**：分组与总量都用 `count(DISTINCT currency)` 判断，`>1` 时 `estimatedCost` 与 `currency` 置 `null`，前端展示「多币种」；无数据时各项为 `0` 或空数组，不造假。
- `byProvider` / `byModel` 按调用量倒序，最多 20 条。

#### 9.6.3 GET /api/v1/admin/model-connections

只读分页，参数 `page` / `size` / `userId`（UUID）/ `provider` / `status`（`ACTIVE` / `DELETED`）。响应条目包含 `username`、`displayName`、`providerName`、`baseUrl`、`lastVerifiedAt` 与 `credential {id, maskedHint, status, createdAt}`；无有效凭证时 `credential` 为 `null`。

- **安全边界**：Mapper 只提供查询方法，SQL 只选 `masked_hint` 与凭证状态，不选 `ciphertext`、`key_version`，也不关联用户密钥；接口层无创建、验证、删除入口。
- 状态包含 `DELETED` 是为了排查「用户为什么看不到连接」，不改变用户侧只返回有效连接的语义。

## 10. 错误码

| code | HTTP | 场景 |
| --- | --- | --- |
| `10001` | 400 | 请求参数不合法（校验失败，`data` 为字段列表） |
| `10002` | 400 | 缺少必要参数或请求头 |
| `10003` | 400 | 参数类型不正确 |
| `10004` | 400 | 请求体格式不正确 |
| `10005` | 405 | 请求方法不支持 |
| `10006` | 415 | 请求内容类型不支持 |
| `10007` | 429 | 登录失败限流：同一 IP + 用户名 60 秒窗口内失败 5 次后，第 6 次返回（**已实现，进程内单实例**） |
| `20001` | 401 | 未认证或凭证失效 |
| `20002` | 403 | 已认证但无权限（含非 `ADMIN` 访问 `/api/v1/admin/**`）；或 `/auth/refresh`、`/auth/logout` 的来源校验未通过 |
| `30000` | 400 | 通用业务失败 |
| `30001` | 404 | 资源不存在（含管理端目标用户不存在） |
| `30002` | 409 | 资源状态冲突：删除当前设备会话、禁用自己、移除最后一个启用 `ADMIN` |
| `40102` | 400 | 当前口令不正确（`IdentityErrorCode.CURRENT_PASSWORD_INVALID`） |
| `40103` | 400 | 新口令与当前口令相同（`IdentityErrorCode.PASSWORD_UNCHANGED`） |
| `40104` | 409 | 邮箱已被其他账号占用（`IdentityErrorCode.EMAIL_TAKEN`） |
| `40105` | 404 | 会话不存在或不属于当前用户（`IdentityErrorCode.SESSION_NOT_FOUND`） |
| `40201` | 429 | 每日请求额度已用尽（`QUOTA_EXCEEDED`），`data` 带额度详情 |
| `40202` | 403 | 模型不存在或当前账号不可用（`MODEL_NOT_AVAILABLE`） |
| `40203` | 422 | 当前模型不支持所需能力（`CAPABILITY_UNSUPPORTED`） |
| `40204` | 404 | 模型运行时未启用（`RUNTIME_DISABLED`） |
| `40205` | 401 | 服务身份校验失败（`SERVICE_TOKEN_INVALID`） |
| `40206` | 404 | 运行时任务不存在或已失效（`TASK_NOT_FOUND`） |
| `40207` | 401 | `X-User-Token` 无效或已失效（`USER_TOKEN_INVALID`） |
| `40208` | 400 | 模型标识格式不正确（`MODEL_REFERENCE_INVALID`） |
| `40209` | 404 | BYOK 未启用（`ModelErrorCode.BYOK_DISABLED`） |
| `40210` | 404 | 模型连接不存在或不属于当前用户（`CONNECTION_NOT_FOUND`） |
| `40211` | 400 | Provider 不存在或未启用（`PROVIDER_NOT_SUPPORTED`） |
| `40212` | 409 | 同一 Provider 已有 ACTIVE 连接（`CONNECTION_EXISTS`） |
| `40213` | 500 | 凭证密文损坏或主密钥不匹配（`CREDENTIAL_CORRUPTED`） |
| `40214` | 400 | 接入地址协议或主机不合法（`BASE_URL_INVALID`） |
| `40215` | 409 | 凭证已兑换，需重新发起请求（`CREDENTIAL_LEASE_CONSUMED`） |
| `40216` | 401 | BYOK 凭证已撤销或不可用（`CREDENTIAL_REVOKED`） |
| `40217` | 502 | 凭证验证失败或上游不可用（`CREDENTIAL_VERIFY_FAILED`） |
| `40218` | 409 | 非 BYOK 任务无需兑换（`LEASE_NOT_BYOK`） |
| `40219` | 422 | Provider 拒绝该凭证（`CREDENTIAL_REJECTED`） |
| `40220` | 409 | 幂等键已用于其他请求，或原任务已过期（`IDEMPOTENCY_CONFLICT`） |
| `40221` | 409 | 同一生效时间已存在定价版本（`ModelErrorCode.PRICING_VERSION_EXISTS`） |
| `50000` | 500 | 系统异常（不返回内部细节） |
| `50001` | 503 | 依赖服务不可用 |

`4xxxx` 为业务模块专用区间。当前已登记：`40102` / `40103` 改密失败、`40104` 邮箱冲突、`40105` 设备会话不存在（identity 模块）；`40201`–`40221` 为模型运行时、服务令牌、BYOK 连接与凭证、lease、任务幂等与管理端定价版本（model 模块）。

## 11. 分页约定

`PageQuery` 默认 `page=1`、`size=20`，`size` 上限 100（`@Max`），超限返回 400 `code=10001`，不做静默截断。
`PageResult` 结构为 `{ list, total, page, size }`，`list` 永不为 `null`，`total` 为 0 时直接返回空列表、不再查列表 SQL。

当前使用分页的真实接口：`GET /api/v1/users/me/sessions`、`GET /api/v1/users/me/model-usage`、`GET /api/v2/models`、`GET /api/v2/model-connections`、`GET /api/v1/admin/users`、`GET /api/v1/admin/audit-logs`、`GET /api/v1/admin/models`、`GET /api/v1/admin/models/{provider}/{modelKey}/pricing`、`GET /api/v1/admin/model-usage`、`GET /api/v1/admin/model-connections`。

兼容说明：`GET /api/v1/models` 与 `GET /api/v1/model-connections` 仍返回裸数组；分页版本已在 `/api/v2` 提供，前端已于 2026-11-01 切换，v1 暂不删除（见 §7.9）。

## 12. 契约变更影响

修改本文件涉及的路径、字段、错误码时，必须同步：`application-service` 的 DTO 与 `docs/`、前端类型（`frontend/src/features/<domain>/api/`）、Agent 侧 Schema（`agent-service/app/services/control_plane.py` 及对应 Pydantic 模型）与根 `docs/api-contract.md`。刷新令牌相关字段（Cookie 名、Path、SameSite、过期期限）属于跨端契约，改动必须同时通知前端（`frontend/src/features/auth/model/auth-session.ts` 负责会话恢复）与运维（`AUTH_COOKIE_SECURE` 与 HTTPS 部署）。

## 13. 权威文档导航

| 主题 | 权威文档 |
| --- | --- |
| 文档总入口 | [`docs/README.md`](../../README.md) |
| 系统架构与服务边界 | [`docs/architecture-overview.md`](../../architecture-overview.md) |
| 对外与内部接口契约摘要 | [`docs/api-contract.md`](../../api-contract.md) |
| 本服务架构与数据 | [`architecture.md`](./architecture.md) |
| 本服务安全说明 | [`security.md`](./security.md) |
| 本服务开发指南 | [`development-guide.md`](./development-guide.md) |
| 环境变量唯一清单 | [`docs/deployment/environment-variables.md`](../../deployment/environment-variables.md) |
| Java 编码硬约束 | [`.trae/rules-on-demand/20-backend-java.md`](../../../.trae/rules-on-demand/20-backend-java.md) |
