# Java 业务端安全说明

| 项 | 内容 |
| --- | --- |
| 状态 | 已验证（配置、签发、校验、刷新会话、异常输出、限流与审计写入均有代码证据） |
| 基线 | `main`（2026-11-01 复核） |
| 最后核验 | 2026-11-01 |
| 主要证据 | `shared/config/SecurityConfig.java`、`AppSecurityProperties.java`、`CorsProperties.java`、`ProdConfigGuard.java`、`shared/security/TokenUseFilter.java`、`identity/**`、`db/migration/V2__create_users.sql`、`V3__create_refresh_sessions.sql`、`V6__create_auth_audit_logs.sql` |

## 1. 信任边界

- 唯一公网入口是 Nginx；本服务端口仅内网可达（2026-10-28 通信决策）。
- 前端不参与安全判定；前端隐藏入口只影响交互。
- 本服务是 Token 的**唯一签发方**；Agent 只验证，不建用户表、不签发生产 Token。

## 2. 认证

**双令牌模型**：短生命周期 Access Token 走请求头，长期 Refresh Token 只走 HttpOnly Cookie。

| 项 | 事实 |
| --- | --- |
| 会话模型 | 无状态（`SessionCreationPolicy.STATELESS`），关闭 CSRF（改用 Origin 校验，见 §5） |
| Access Token 算法 | **RS256**，私钥 `JWT_PRIVATE_KEY`（PKCS#8 PEM）签发，公钥 `JWT_PUBLIC_KEY`（X.509 PEM）验签；两端都不允许算法协商降级 |
| 密钥标识 | JWS Header 带 `kid`（`JWT_KID`，默认 `rsa-2026-10`），Agent 按 `kid` 选公钥 |
| Access Token 校验 | 签名、`exp`（默认校验器）、`iss`（`JwtValidators.createDefaultWithIssuer`）、**`aud`（强制）** |
| Access Token Claims | `iss`、`iat`、`exp`、`aud`、`jti`、`sub`（`users.public_id`，UUID）、`roles`、`token_use="access"`、`sid`（签发时所在 `refresh_sessions.family_id`，只用于标记当前设备会话，不参与鉴权） |
| 角色映射 | `roles` claim → `ROLE_` 前缀权限（`JwtAuthenticationConverter`） |
| Access Token 有效期 | `JWT_ACCESS_TTL`，默认 `10m` |
| Refresh Token | 32 字节随机串（Base64URL 43 字符），不透明、不可解析；库内只存 SHA-256 摘要 |
| Refresh 存放 | `HttpOnly` Cookie `agent_refresh`，`SameSite=Strict`，`Path=/api/v1/auth`，`Secure` 由 `AUTH_COOKIE_SECURE` 控制（prod 强制 `true`） |
| Refresh 过期 | 双重：闲置 `AUTH_REFRESH_IDLE_TTL`（默认 `7d`）+ 绝对 `AUTH_REFRESH_ABSOLUTE_TTL`（默认 `30d`，轮换不延长） |
| 轮换 | 每次 `/auth/refresh` 换发新令牌并把旧令牌标记 `rotated`（写 `replaced_by_id`） |
| 重放检测 | 超过宽限期（`AUTH_REFRESH_ROTATION_GRACE`，默认 `60s`）再次出示旧令牌，按 `family_id` 整族撤销（`revoked_reason=replay`） |

用户来源：`users` / `user_identities` 表（V2 迁移）。`users.public_id` 是对外唯一标识，写入 JWT `sub` 与所有响应；`users.id`（BIGINT 自增）只在库内使用，绝不对外暴露。`BootstrapUserSeeder` 按 `app.security.bootstrap-users` 在启动时为不存在的用户名播种账号，口令经 BCrypt 编码，留空则跳过。

## 3. 刷新会话存储

`refresh_sessions`（V3 迁移）关键列：

| 列 | 用途 |
| --- | --- |
| `token_hash` `CHAR(64)` UNIQUE | SHA-256 摘要；拖库也无法还原可用令牌 |
| `family_id` `UUID` | 一次登录派生的整条轮换链，重放时整族撤销 |
| `absolute_expires_at` / `idle_expires_at` | 绝对上限与闲置期限，两者都过期即撤销 |
| `revoked_at` / `revoked_reason` | 撤销时间与原因（`logout` / `expired` / `replay` / `user_disabled` / `password_change`） |
| `replaced_by_id` | 轮换出的新会话，用于区分正常轮换与重放 |

- 索引：`user_id`（按用户清理 / 退出所有设备）、`family_id`（重放时按族撤销）。
- 用户被禁用时整族撤销（`user_disabled`），避免继续换发新令牌。
- 改密成功后撤销该用户除当前族之外的全部会话（`password_change`）：其他设备下次刷新即失败，当前设备不受影响。当前族由访问令牌的 `sid` claim 识别，不依赖刷新 Cookie（其 `Path` 限定在 `/api/v1/auth`）。
- `login` 开启新族；`refresh` 锁定行后轮换；`logout` 幂等撤销当前会话并清 Cookie。
- 设备会话管理（PR 5）：`GET /users/me/sessions` 按 `family_id` 聚合，同一登录的轮换链只算一台设备；`DELETE /users/me/sessions/{familyId}` 的归属校验下推到 SQL 的 `user_id` 条件，因此「他人的族」与「不存在」返回同一个 404 `40105`，不泄露他人会话是否存在；目标为当前设备时返回 409 `30002`，必须改走 `/auth/logout` 以同步清 Cookie。`POST /auth/logout-all` 按 `user_id` 撤销全部有效会话（`logout`）。
- 过期未清理的会话额外保留 7 天用于排查，再由 `purgeExpired()` 删除。

## 4. 授权

`SecurityFilterChain` 规则（顺序敏感）：

| 匹配 | 规则 |
| --- | --- |
| `POST /api/v1/auth/login`、`/refresh`、`/logout` | 放行（三者靠账号口令或 HttpOnly Cookie 自证；后两者另有 Origin 校验） |
| `/v3/api-docs/**`、`/swagger-ui/**`、`/swagger-ui.html` | 放行 |
| `/actuator/health`、`/actuator/info`、`/error` | 放行 |
| `/api/v1/admin/**` | 需 `ADMIN` 角色 |
| 其余 | 需认证 |

- `@EnableMethodSecurity` 已开启，但**当前没有任何 `@PreAuthorize` 使用**；授权完全由路径规则决定。
- `/api/v1/admin/**` 尚无控制器，该规则目前只对未来接口生效。

## 5. 401 / 403 输出与来源校验

安全过滤器链的异常不进入 `@RestControllerAdvice`，由以下组件单独输出，保证结构一致：

| 组件 | 触发 | 输出 |
| --- | --- | --- |
| `RestAuthenticationEntryPoint` | 无 Token、非法、过期、issuer/audience 不符 | 401，`code=20001` |
| `RestAccessDeniedHandler` | 已认证但无权限 | 403，`code=20002` |
| `SecurityResponseWriter` | 两者共用的 JSON 写出器 | `application/json;charset=UTF-8` |

**Origin 校验**（`RequestOriginValidator`）：`/auth/refresh` 与 `/auth/logout` 是仅靠 Cookie 认证的写接口，存在被跨站页面伪造的风险。服务端要求 `Origin`（缺失时退回 `Referer`）命中 `CORS_ALLOWED_ORIGINS` 白名单，或与请求 `Host` 同源，否则返回 403 `20002`。这是 `SameSite=Strict` 之外的服务端兜底；畸形 `Referer` 直接视为不可信。

响应体与业务接口同为 `{code, message, data?, requestId}`，并回写 `X-Request-Id`。

## 6. CORS

`CorsProperties` / `CorsConfig` 装配，`SecurityConfig` 的 `cors(withDefaults())` 生效。

| 项 | 默认 |
| --- | --- |
| `allowedOrigins` | 空（**不放开任何来源**）；`local` profile 默认 `http://localhost:5173` |
| `allowedMethods` | GET/POST/PUT/PATCH/DELETE/OPTIONS |
| `allowedHeaders` | `*` |
| `exposedHeaders` | `X-Request-Id` |
| `allowCredentials` | `false` |
| `maxAge` | 1h |

配置项 `CORS_ALLOWED_ORIGINS` 为逗号分隔白名单；留空即不放开跨域。同源部署（经 Nginx）时不依赖 CORS 携带 Cookie，因此 `allowCredentials` 保持 `false`；分域部署若需跨域携带刷新 Cookie，必须显式开启并同时限制具体来源，禁止 `*`。

## 7. 生产配置守卫

`ProdConfigGuard` 通过 `META-INF/spring.factories` 注册为 `ApplicationContextInitializer`，在容器 refresh 前执行，仅当 `prod` profile 激活时生效。任一项不通过即抛异常阻止启动：

| 检查 | 判定 |
| --- | --- |
| `debug` | 为 `true` 直接拒绝 |
| `app.security.jwt.private-key` | 空 / 未解析占位符 / 默认占位词 / 非 PKCS#8 PEM 拒绝 |
| `app.security.jwt.public-key` | 空 / 未解析占位符 / 默认占位词 / 非 X.509 PEM 拒绝 |
| RSA 密钥对 | 私钥与公钥模数不一致（错配）拒绝 |
| `app.security.jwt.audience` | 空或占位符拒绝 |
| `app.security.cookie.secure` | 不为 `true` 拒绝（刷新令牌不允许走明文 http） |
| `spring.datasource.url` | 空或未解析占位符拒绝 |
| `spring.datasource.password` | 空 / 未解析占位符 / 默认占位词拒绝 |

错误信息只含属性名与原因，不输出真实密钥。测试类 `ProdConfigGuardTests` 覆盖各类非法输入。

## 8. 日志与敏感信息

- 登录失败、权限不足、来源不可信记 `WARN` 且不带堆栈；未预期异常记 `ERROR` 且只打一次堆栈。
- 刷新令牌、Access Token 一律不写日志；Cookie 不进日志。
- 401/403 只记录异常类名，不记录 Token 内容。
- 响应与日志均不输出 Token、密码、堆栈、SQL；响应体永不含刷新令牌。

## 9. 已实现能力与已知缺口

2026-11-01 复核：登录失败限流、认证审计写入、设备会话管理曾被本文写成「未实现」，实际均已落地；下表保留它们的真实限制。

| 项 | 现状 | 风险 / 限制 |
| --- | --- | --- |
| 登录失败限流 | **已实现**：`InMemoryLoginAttemptLimiter` 按「客户端 IP + 用户名」计数，60 秒窗口内失败 5 次后第 6 次返回 429 `10007`，成功登录清零；IP 依次取 `X-Forwarded-For` 首段、`X-Real-IP`、`remoteAddr` | 计数存进程内存、重启即清空，**仅单实例有效**；多副本需换成共享存储（如 Redis），接口层无需改动 |
| 认证审计写入与查询 | **已实现**：`AuthAuditRecorder` 在独立事务（`REQUIRES_NEW`）写 `auth_audit_logs`（V6），覆盖 8 类事件（含 `role_changed`）；审计写入失败只记 `warning`，不影响主流程。查询走 `GET /api/v1/admin/audit-logs`（需 `ADMIN`） | 查询只返回事件、登录名、IP 与发生时间，不含 User-Agent 与请求 ID；V18 已为 `event` + `created_at` 建索引 |
| 设备会话管理 | **已实现**：`GET /api/v1/users/me/sessions`、`DELETE /api/v1/users/me/sessions/{familyId}`、`POST /api/v1/auth/logout-all`；前端设备会话组件为 `frontend/src/features/settings/components/device-sessions.tsx` | 未采集 IP / User-Agent，列表只显示族 ID 与时间；当前设备不能直接删除（409 `30002`），必须走 `/auth/logout` 以清 Cookie |
| 无 Access Token 黑名单 | 令牌到期前一直有效（默认 10 分钟） | 无法立即作废单个访问令牌；可撤销刷新会话阻断续期 |
| Agent 可自签 Token | Agent 的 `/auth/dev-token` 在 `app_env=dev` 且 `debug=true` 时签发 Token | 仅本地；生产/预发直接 403。定位为开发工具，不属契约 |
| 单密钥对 | 只有一对 RSA 密钥，`kid` 预留轮换能力但未实现多钥并存 | 密钥轮换需短暂同时支持旧公钥，当前只能一次性切换 |
