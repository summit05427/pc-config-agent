# Java 业务端开发指南

| 项 | 内容 |
| --- | --- |
| 状态 | 已验证（命令、profile、分层、迁移与测试均与代码一致） |
| 最后核验 | 2026-11-01 |
| 主要证据 | `application-service/pom.xml`、`src/main/resources/application*.yaml`、`src/main/resources/db/migration/*.sql`、`src/test/java/**`、`.github/workflows/ci.yml` |
| 适用范围 | `application-service/**` 的日常开发约定 |

## 1. 适用范围

本文写 `application-service/` 的命令、profile、环境变量入口、分层落位、新增接口与模块步骤、Flyway 规则、测试策略、提交门禁与常见坑。架构与模块事实见 [architecture.md](./architecture.md)，接口字段与错误码见 [api-reference.md](./api-reference.md)，认证与授权见 [security.md](./security.md)。

## 2. 命令（在 `application-service/` 下执行）

| 命令 | 作用 | 备注 |
| --- | --- | --- |
| `.\mvnw.cmd spring-boot:run` | 本地启动，默认 `local` profile | 自动读取仓库根 `.env`（须在 `application-service/` 目录启动）；无 `.env` 时需手注入变量 |
| `.\mvnw.cmd test` | 仅跑测试 | `test` profile 不连库，可离线执行；Testcontainers 用例需要 Docker |
| `.\mvnw.cmd verify` | 编译 + 测试 + 生成 JaCoCo 报告 | 提交前必须通过 |
| `.\mvnw.cmd package` | 打包可执行 JAR 到 `target/` | 生产镜像由 Dockerfile 构建 |
| `.\mvnw.cmd -o verify` | 离线模式，只用本地仓库缓存 | 无网络时的替代方案 |
| `.\mvnw.cmd dependency:tree` | 查看依赖树 | 排查版本冲突 |

Linux/macOS 把 `.\mvnw.cmd` 换成 `./mvnw`。CI 的 Java 任务在 `application-service/` 下执行 `./mvnw -B -ntp verify`，并归档 `target/site/jacoco/`。

**本项目没有配置代码格式化或静态检查插件**（`pom.xml` 中只有 `spring-boot-maven-plugin`、`jacoco-maven-plugin`、`maven-compiler-plugin`），因此 `verify` 不包含格式校验，风格约束依赖 [`.trae/rules-on-demand/20-backend-java.md`](../../../.trae/rules-on-demand/20-backend-java.md) 与评审。

Maven Wrapper 已锁定 Maven 版本（`.mvn/wrapper/`），无需本地安装 Maven；需要 JDK 21。

## 3. profile

| profile | 数据库 | Flyway | springdoc | 用途 |
| --- | --- | --- | --- | --- |
| `local`（默认） | `DB_URL` 默认 `jdbc:postgresql://127.0.0.1:${POSTGRES_PORT:5432}/agent`，账号取 `POSTGRES_USER`、口令取 `POSTGRES_PASSWORD` | 开启 | 开启 | 日常开发，配合根 Compose 的 `postgres`（模板宿主端口 15432） |
| `dev` | `DB_URL` 默认同上，读根 `.env` | 开启 | 开启 | 服务器同机联调 |
| `prod` | `DB_URL` / `DB_USERNAME` / `DB_PASSWORD` 无默认值，缺失即启动失败 | 开启 | 关闭 | 生产发布，受 `ProdConfigGuard` 前置校验 |
| `test` | 默认指向 `agent_test`，`initialization-fail-timeout: -1` 让连接池不在启动期建连 | **关闭** | 开启 | 自动化测试，不依赖真实数据库 |

切换方式：`$env:SPRING_PROFILES_ACTIVE="dev"`（PowerShell）或 `-Dspring-boot.run.profiles=dev`。

全部 yaml 中**没有 `server.port` 配置**，端口取 Spring Boot 默认 `8080`；容器内端口同为 `8080`。

## 4. 环境变量

环境变量的唯一权威清单见 [`docs/deployment/environment-variables.md`](../../deployment/environment-variables.md)，以根 `.env.example` 与各服务 `.env.example` 为机读源。本文不复制变量默认值，只说明分组与本服务侧约束：

| 分组 | 用途 | 注意 |
| --- | --- | --- |
| `DB_*` | 数据源与 Hikari 连接池 | `prod` 下无默认值，缺失即启动失败 |
| `JWT_*` | RS256 密钥、`kid`、issuer、audience、Access Token TTL | 私钥只注入本服务；公钥与 Agent 共享；密钥必须成对 |
| `AUTH_*` | 刷新令牌 TTL、轮换宽限期、Cookie `Secure`、引导账号 | `prod` 下 Cookie 必须 `Secure` |
| `CORS_ALLOWED_ORIGINS` | 跨域白名单，也是 `/auth/refresh`、`/auth/logout` 的 Origin 校验依据 | 留空即不放开跨域 |
| `MODEL_RUNTIME_ENABLED` / `BYOK_ENABLED` | 模型运行时与 BYOK 总开关 | 关闭时相关接口返回 404，不改变既有行为 |
| `MODEL_CRED_MASTER_KEY` / `MODEL_CRED_MASTER_KEYS` / `MODEL_CRED_KEY_VERSION` | BYOK 凭证加密主密钥与轮换密钥环 | 启用 BYOK 时缺失即启动失败 |
| `INTERNAL_AUTH_CLIENT_ID` / `INTERNAL_AUTH_CLIENT_SECRET` / `INTERNAL_AUTH_TOKEN_TTL` | Agent 换取服务令牌的客户端凭据 | 启用模型运行时后密钥为空即启动失败 |
| `MODEL_TASK_TTL` / `MODEL_QUOTA_DAILY_REQUESTS` / `MODEL_DEFAULT_KEY` | 任务 TTL、每日额度、Auto 默认模型 | 影响内部接口行为 |
| `MODEL_RECONCILE_*` / `MODEL_TASK_CLEANUP_*` | 对账与任务清理定时任务 | cron 为 UTC；yaml 里加引号，根 `.env` 里**不要**加引号（`.env` 由 properties 解析） |
| `MODEL_GATEWAY_BASE_URL` / `MODEL_GATEWAY_MASTER_KEY` | LiteLLM 网关地址与 master key | 凭证探测经网关完成，Java 不再持有 Provider 默认地址 |

`test` profile 把测试用 JWT 密钥对、引导账号口令与 CORS 白名单写死在 `application-test.yaml`，所以跑测试不需要外部环境变量。测试密钥仅供本地/CI，禁止复用到生产。

`application-service/.env.example` 只服务于其自带的 `docker-compose.yml`（`POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`），与 Java 运行时变量是两套，不要混用。

## 5. 分层与落位

依赖方向 `web → application → domain / infrastructure`，`shared/**` 为技术公共层，两个业务模块互不引用对方内部实现。

| 目录 | 放什么 | 不放什么 |
| --- | --- | --- |
| `identity/web` | `AuthController`、`UserProfileController`、`UserPasswordController`、`UserSessionController`、`UserPreferenceController`、`AdminUserController`、`AdminAuditLogController`、`RefreshCookieFactory`、`web/dto` 请求/响应 record | 事务、密码校验逻辑 |
| `identity/application` | `AuthService`（编排）、`RefreshSessionService`（事务）、`UserProfileService`、`UserPasswordService`、`UserPreferenceService`、`AdminUserService`、`AdminAuditLogService`、`AuthAuditRecorder`、`AuthAuditQuery`、`LoginAttemptLimiter` | `HttpServletRequest`、`ResponseEntity` |
| `identity/domain` | `UserAccount`、`AuthenticatedUser`、`RefreshSession`、`RefreshTokens`、`UserPreference`、`AuthAuditEvent`、`IdentityErrorCode` | 持久化注解 |
| `identity/infrastructure` | `JwtTokenService`、`BootstrapUserSeeder`、`DatabaseUserDetailsService`、`MyBatis*` 实现、Mapper、`InMemoryLoginAttemptLimiter`、`RefreshSessionCleanupJob` | 对外 DTO |
| `model/web` | 模型目录、连接、用量与内部接口 Controller，`web/dto` record | 事务、凭证加解密 |
| `model/application` | `ModelCatalogService`、`ModelRuntimeService`、`ModelUsageService`、`ProviderConnectionService`、`CredentialLeaseService`、`ServiceTokenService`、`UserTokenValidator` | HTTP 对象 |
| `model/domain` | `ModelErrorCode`、`ModelReference`、`ModelTaskView`、`CredentialLease`、`CredentialMasker`、`BaseUrlPolicy` 等 | 持久化注解 |
| `model/infrastructure` | `ModelCatalogMapper`、`RuntimeTaskMapper`、`QuotaMapper`、`UsageMapper`、`ProviderConnectionMapper`、`ProviderCredentialMapper`、`ModelPricingMapper`、清理与对账 Job | 对外 DTO |
| `shared/api` | `ApiResponse`、`PageQuery`、`PageResult`、`FieldViolation` | 业务字段 |
| `shared/error` | `ErrorCode`、`CommonErrorCode`、`BusinessException` | HTTP 状态装配 |
| `shared/web` | `RequestIdFilter`、`RequestMetadataFilter`、`ClientIpResolver`、`RequestContext`、`GlobalExceptionHandler` | 业务分支 |
| `shared/security` | `TokenUseFilter`、`TokenClaims`、`CurrentUser`、`JwtKeyLoader`、`RequestOriginValidator`、401/403 输出 | 具体鉴权规则 |
| `shared/config` | `SecurityConfig`、`CorsConfig`、`OpenApiConfig`、`ProdConfigGuard`、`AppSecurityProperties`、`CorsProperties`、`ModelRuntimeProperties`、`MybatisConfig` | 业务流程 |

新增数据库访问时沿用同一模块的 `infrastructure` 位置，事务注解只标在 `application` 层 public 方法。

## 6. 新增一个接口

1. **DTO 先行**：在对应模块的 `web/dto` 下建 `record`，字段上用 `@NotBlank` / `@Size` / `@Pattern` 等声明约束；请求 DTO 加 `@Valid`，禁止用 `Map` 承载业务字段。
2. **Service 承接业务**：逻辑写在 `<module>/application` 下，失败抛 `BusinessException`；需要新错误码时在对应模块的错误码枚举（如 `IdentityErrorCode`、`ModelErrorCode`）中加项，并保证区间与全局唯一。
3. **Controller 只做转发**：`@RestController` + `@RequestMapping("/api/v1/<资源复数>")`，方法上用 `@Valid @RequestBody` 或参数级约束（`@RequestParam` 上直接写 `@Min` / `@Max`，**不要**在类上加 `@Validated`）。
4. **统一返回**：成功用 `ApiResponse.success(data)`，无数据用 `ApiResponse.success()`；HTTP 状态由错误码枚举携带，不要在 Controller 里手写 `ResponseEntity.status(...)`。需要写 Cookie 时返回 `ResponseEntity` 并在 `Set-Cookie` 上设置 `HttpOnly`，禁止把令牌塞进响应体。
5. **补 OpenAPI 描述**：`@Operation` / `@Schema` 按需补充，`OpenApiConfig` 已注册 `bearerAuth` 安全方案。
6. **补测试**：至少覆盖成功、参数非法、未认证/无权限、资源不存在四类，见 §9。
7. **同步契约**：路径或字段变化时，同步前端 `frontend/src/features/<domain>/api/`、Agent 侧调用的 Schema、根 `docs/api-contract.md` 与本服务 `api-reference.md`。
8. **纯 Cookie 驱动的写接口**：除了 `SameSite`，必须在服务端用 `RequestOriginValidator` 校验请求来源，参照 `/auth/refresh` 与 `/auth/logout`。
9. **内部接口**：新增 `/internal/v1/**` 时，鉴权由 `TokenUseFilter` 与 `SecurityConfig` 的 scope 规则承接；需要代表用户时额外读 `X-User-Token` 并走 `UserTokenValidator`，禁止从请求体取用户身份；写接口按需支持 `Idempotency-Key`。

## 7. 新增一个业务模块

1. 在 `src/main/java/com/example/agent/<module>/` 建 `package-info.java`，标注 `@ApplicationModule`。模块发现策略是 `explicitly-annotated`（`application.yaml` 的 `spring.modulith.detection-strategy`），**未标注的包不会被当模块，也不会受依赖规则约束**。
2. 按需建 `web` / `application` / `domain` / `infrastructure`，只在有内容时才建目录。
3. 模块间只依赖对方根包下公开的类型，禁止直接引用对方的 `application` / `infrastructure` 实现；`ApplicationModuleTests` 会校验循环依赖与非法引用。
4. 需要建表时先写迁移脚本（§8），再写 `infrastructure` 下的 Mapper。
5. 首次引入事务时，`@Transactional` 只标在 `application` 层的 public 方法上，查询标 `readOnly = true`。

## 8. Flyway 与数据库

- 迁移目录：`src/main/resources/db/migration`，当前共 **21 个脚本（V1–V21）**，最高版本 `V21`。逐版本内容见 [architecture.md §7](./architecture.md#7-数据访问现状)。
- 现有版本按业务分组：
  - 身份：`V1__baseline.sql`、`V2__create_users.sql`、`V3__create_refresh_sessions.sql`、`V4__extend_users_profile.sql`、`V5__create_user_preferences.sql`、`V6__create_auth_audit_logs.sql`、`V18__add_user_admin_indexes.sql`
  - 模型：`V7__create_model_catalog.sql`、`V8__create_model_runtime_tasks.sql`、`V9__create_model_usage_records.sql`、`V10__create_model_request_quotas.sql`、`V11__create_provider_connections.sql`、`V12__create_provider_credentials.sql`、`V13__add_model_task_lease.sql`、`V14__clear_provider_default_base_url.sql`、`V15__add_model_task_idempotency.sql`、`V16__create_model_pricing.sql`、`V17__fix_deepseek_model_catalog.sql`、`V19__add_admin_query_indexes.sql`、`V20__seed_model_pricing_sample.sql`、`V21__disable_openai_model_catalog.sql`
- 已合入主干的脚本只可追加、不可修改；新增迁移按顺序从 `V22` 起编号。
- 禁止手工改库；生产禁止无 `WHERE` 的 `UPDATE` / `DELETE`。
- SQL 全部参数化；`mybatis.mapper-locations` 指向 `classpath*:mapper/**/*.xml`，`map-underscore-to-camel-case` 已开启，Mapper XML 放在 `src/main/resources/mapper/`。
- `refresh_sessions` 只存令牌的 SHA-256 摘要，永远不会写入原始刷新令牌；排查问题时只按 `family_id` 或 `user_id` 聚合查。
- `RefreshSessionCleanupJob` 定期清理过期超过 7 天的会话行，保留窗口用于排障，不要缩短。
- 本地库：在 `application-service/` 下执行 `docker compose up -d`，仅绑定 `127.0.0.1:5432`。
- 连接云端库联调走 SSH 隧道，口令只以临时环境变量注入，禁止写进仓库。

## 9. 测试策略

`src/test/java` 下共 46 个 `.java` 文件（38 个测试类 + 8 个测试支撑类），完整清单见 [architecture.md §8](./architecture.md#8-测试结构)。

| 测试类 | 启动容器 | 覆盖内容 |
| --- | --- | --- |
| `AgentApplicationServiceApplicationTests` | 是（`@SpringBootTest`，`test` profile） | 上下文可加载 |
| `ApplicationModuleTests` | 否 | `ApplicationModules.of(...).verify()`，校验模块依赖与循环依赖 |
| `PublicApiContractTests` | 否（standalone MockMvc） | 响应信封、`X-Request-Id` 复用、分页默认值与 `size ≤ 100`、异常映射、系统异常不泄露堆栈与密码 |
| `SecurityIntegrationTests` | 是（`@SpringBootTest` + `@AutoConfigureMockMvc`） | 登录成功/失败、`me` 带/不带 Token、受保护接口 401、ADMIN 403、`/v3/api-docs` 匿名可达、CORS 预检、`expiresIn=600`、响应体不含刷新令牌 |
| `TokenUseFilterTests` | 否（纯单测） | 服务令牌与访问令牌的路径隔离 |
| `RefreshFlowTests` | 是（`@SpringBootTest` + 内存实现） | Cookie 属性、令牌轮换、缺 Cookie、来源不可信、宽限期内重放、退出幂等 |
| `RefreshSessionServiceTests` | 否（内存 `RefreshSessionStore`） | 双重过期、重放撤族、用户禁用撤族 |
| `RefreshSessionPersistenceTests` / `UserPersistenceTests` | 是（Testcontainers，PostgreSQL） | Mapper SQL、唯一约束与外键 |
| `UserProfileServiceTests` / `UserProfileApiTests` | API 测试走完整过滤器链 | 资料读写、字段裁剪、邮箱冲突 `40104` |
| `UserPasswordServiceTests` / `UserPasswordApiTests` | API 测试走完整过滤器链 | 改密、令牌缺 `sid`、撤销其他设备 |
| `UserSessionApiTests` | 是 | 设备列表与踢出、当前设备 409、越权 404 |
| `UserPreferenceServiceTests` / `UserPreferenceApiTests` | API 测试用 Testcontainers | 默认值、枚举与长度校验 |
| `AuthAuditLogTests` | 是（内存审计写入） | 认证审计事件与定位信息 |
| `AdminUserServiceTests` | 否（Mockito） | 列表过滤与分页、禁用撤会话与 `user_disabled` 审计、最后管理员保护、角色变更与 `role_changed` 审计 |
| `AdminUserApiTests` / `AdminAuditLogApiTests` | 是（`@SpringBootTest` + 内存实现） | `/api/v1/admin/users` 与 `/api/v1/admin/audit-logs` 的鉴权、校验、分页与错误码 |
| `LoginRateLimitTests` / `InMemoryLoginAttemptLimiterTests` | 是 / 否 | 429 语义、成功清零、窗口过期 |
| `ModelCatalogServiceTests` / `ModelRuntimeServiceTests` / `ModelUsageServiceTests` | 否（Mockito 或内存依赖） | 目录解析、任务与额度、用量上报 |
| `ModelConnectionApiTests` / `ModelPersistenceTests` | 是（Testcontainers + 真实过滤链） | BYOK 连接、归属校验、响应不含明文/密文、SQL 与约束 |
| `ProdConfigGuardTests` | 否（纯单测，构造 `Environment`） | prod 下 `debug=true`、密钥缺失/错配、默认占位口令、`cookie.secure=false` 被拦截 |

约定：

- 单测不启容器，外部依赖用 Mockito 隔离；集成测试用 `@SpringBootTest`。
- 不涉及数据库的集成测试用 `@Primary` 内存实现（`InMemoryUserDirectory` / `InMemoryRefreshSessionStore` / `InMemoryAuthAuditLog`），并在配置类里注册 `NoOpTransactionManager`——否则 `@Transactional` 会去连真实 PostgreSQL，每个请求卡在连接超时。
- 需要验证真实 SQL 的用 Testcontainers；禁止用「内存实现跑通」当作 SQL 已验证。
- 禁止 `@Disabled`、禁止降断言换通过。
- 测试方法名表达「场景 + 预期」（如 `login_shouldReturnUnauthorized_whenPasswordIsWrong`）。

## 10. 提交门禁

- 提交前执行 `.\mvnw.cmd verify`，`verify` 阶段会生成 `target/site/jacoco` 报告。
- JaCoCo **只生成报告、不设阈值**；覆盖率目标「核心 service ≥ 70%」目前是建议，不是门禁。
- CI 见 `.github/workflows/ci.yml`，按 `application-service/**` 路径触发，执行同一套 `verify`。
- 禁止提交 `target/`、`.env`、`.idea/`、真实密钥。
- 提交信息用 Conventional Commits，如 `feat(model): 新增运行时任务内部接口`。

## 11. 常见坑

1. **缺 `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` 直接启动失败**：这是设计行为（占位符无法解析），不是配置错误。本地跑起来前先注入成对的 RSA 密钥；不配置 `AUTH_ADMIN_PASSWORD` 则不会播种任何账号，登录会一直 401。
2. **`test` profile 不连数据库**：`application-test.yaml` 关闭 Flyway 并让连接池延迟建连，出现「表不存在」时先确认 profile；需要真实 SQL 的用 `*PersistenceTests` / `ModelConnectionApiTests`（Testcontainers），不要用内存实现冒充。
3. **401/403 不走 `GlobalExceptionHandler`**：Spring Security 异常发生在过滤器链，由 `RestAuthenticationEntryPoint` / `RestAccessDeniedHandler` 经 `SecurityResponseWriter` 输出，新增鉴权异常处理时改这里。
4. **Jackson 用的是 3.x 包名**：`SecurityResponseWriter` 导入 `tools.jackson.databind.ObjectMapper`，不是 `com.fasterxml.jackson.*`，混用会编译失败。
5. **`explicitly-annotated` 策略**：新包不加 `@ApplicationModule` 时，`ApplicationModuleTests` 根本看不到它，误以为「已通过」。
6. **引导账号按 `bootstrap-users` 播种**：每个账号自带 `username` / `password` / `roles`，角色写 `ADMIN`（不要写 `ROLE_ADMIN`）；`AuthenticatedUser.getAuthorities()` 会补 `ROLE_` 前缀，库里只存裸角色名；只有用户名不存在时才插入，改口令不会覆盖既有用户。
7. **`prod` 下的 `CORS_ALLOWED_ORIGINS`**：为空即不放开跨域；经 Nginx 同源部署时保持为空即可，直连后端才需要配。
8. **本地 5432 端口冲突**：`application-service/docker-compose.yml` 已占用 `127.0.0.1:5432`；同机再起根 `docker-compose.yml` 的 PostgreSQL 会冲突，二选一启动。
9. **刷新 Cookie 的 `Path=/api/v1/auth`**：前端直连后端（不经 Nginx、且以 `/api/v1` 为基址）时能带上；若把基址改成别的路径，Cookie 不会被携带，表现为「刷新永远 401」。Cookie 名与 Path 属于跨端契约，改动必须同步前端（修复后位置为 `frontend/src/core/http/auth.ts` 与 `frontend/src/features/auth/api/`）。
10. **`Secure` 未开导致本地 http 收不到 Cookie**：`local` profile 默认 `AUTH_COOKIE_SECURE=false`；生产反向不能让 `Secure=false`，`ProdConfigGuard` 会直接阻止启动。
11. **宽限期内的重放不会撤族**：并发刷新（多标签页）在 60 秒内重复出示旧令牌只返回 401，这是防止误伤；只有超期重放才整族撤销。排查「用户被踢下线」时先看 `revoked_reason`。
12. **内部接口不接受用户令牌**：`TokenUseFilter` 会拒绝访问令牌访问 `/internal/v1/**`，也会拒绝服务令牌访问 `/api/v1/**`；内部接口要用 `POST /internal/v1/auth/service-token` 换服务令牌，需要代表用户时再带 `X-User-Token`。
13. **启用模型运行时后内部凭据必填**：`INTERNAL_AUTH_CLIENT_SECRET` 为空、或启用 BYOK 时 `MODEL_CRED_MASTER_KEY` 缺失，都会启动失败；这是 fail-fast，不要用占位值绕过。

## 12. 未实现能力（明确声明）

以下内容在本仓库中**不存在**：

- Access Token 黑名单 / 按用户立即作废单个访问令牌；登出只撤销刷新会话。
- 调用 Agent 的 HTTP 客户端（`WebClient` / `RestTemplate` / `RestClient` / Feign 均无命中）。反方向存在：Agent 用服务令牌调用本服务 `/internal/v1/**`（见 [architecture.md §6](./architecture.md#6-与-agent-的关系c-01-更正)）。

已实现、不要再写成缺口：

- 登录失败限流（`InMemoryLoginAttemptLimiter`，5 次/60s，IP + 用户名，HTTP 429 `10007`；仅单实例有效）。
- 认证审计写入与查询（`AuthAuditRecorder` + `auth_audit_logs`，独立事务；查询走 `GET /api/v1/admin/audit-logs`）。
- 管理端用户与审计接口：`GET /api/v1/admin/users`、`PATCH /api/v1/admin/users/{publicId}/status`、`PATCH /api/v1/admin/users/{publicId}/roles`、`GET /api/v1/admin/audit-logs`（`ADMIN`）。
- 设备会话管理后端接口：`GET /api/v1/users/me/sessions`、`DELETE /api/v1/users/me/sessions/{familyId}`、`POST /api/v1/auth/logout-all`；前端设备会话组件位于 `frontend/src/features/settings/components/device-sessions.tsx`。

## 13. 权威文档导航

| 主题 | 权威文档 |
| --- | --- |
| 文档总入口 | [`docs/README.md`](../../README.md) |
| 系统架构与服务边界 | [`docs/architecture-overview.md`](../../architecture-overview.md) |
| 对外与内部接口契约 | [`docs/api-contract.md`](../../api-contract.md) |
| 本服务架构 | [`architecture.md`](./architecture.md) |
| 本服务接口与错误码 | [`api-reference.md`](./api-reference.md) |
| 本服务安全说明 | [`security.md`](./security.md) |
| 环境变量唯一清单 | [`docs/deployment/environment-variables.md`](../../deployment/environment-variables.md) |
| 跨端变更矩阵与门禁 | [`docs/development-rules.md`](../../development-rules.md) |
| Java 编码硬约束 | [`.trae/rules-on-demand/20-backend-java.md`](../../../.trae/rules-on-demand/20-backend-java.md) |
