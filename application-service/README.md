# agent-application-service

Java 业务端：**访问令牌与服务令牌的唯一签发方**，负责身份认证、用户资料 / 偏好 / 设备会话、模型目录与运行时控制面、BYOK 连接与用量计量。

代码按 Spring Modulith 显式模块拆分：`identity`（身份与账户）、`model`（模型运行时控制面）、`shared`（配置、安全、错误、通用 Web）。接口清单与字段细节见根 `docs/services/application-service/api-reference.md`，本文件只做上手入口，不重复契约与变量表。

## 技术栈

| 类别 | 选型 |
| --- | --- |
| 语言 / 运行时 | Java 21 |
| 框架 | Spring Boot 4.1.1（Spring Framework 7）、Spring Modulith 2.1.2（`detection-strategy: explicitly-annotated`） |
| 安全 | Spring Security 7 OAuth2 Resource Server，RS256 JWT，无状态 |
| 持久层 | MyBatis（starter 4.1.0）+ Flyway（`classpath:db/migration`）+ PostgreSQL |
| 文档 | springdoc-openapi 3.1.1（`/v3/api-docs`、`/swagger-ui.html`，`prod` 关闭） |
| 测试 / 覆盖率 | JUnit 5、Testcontainers（PostgreSQL）、JaCoCo 0.8.13（`verify` 阶段出报告） |

## 模块

| 模块（包） | 职责 | 入口类 |
| --- | --- | --- |
| `com.example.agent.identity` | 登录、刷新轮换、登出、当前用户、资料 / 口令 / 设备会话 / 偏好、认证审计 | `identity/web/AuthController.java` |
| `com.example.agent.model` | 模型目录、BYOK 连接与凭证、运行时任务、每日额度、使用明细、服务令牌、内部接口 | `model/web/ModelRuntimeInternalController.java` |
| `com.example.agent.shared` | JWT 与过滤链、CORS、请求上下文、统一响应与异常、生产配置守卫 | `shared/config/SecurityConfig.java` |

依赖方向固定为 `web → application → infrastructure`；两个业务模块当前互不引用，公共能力放 `shared`，结构由 `ApplicationModuleTests` 调用 Modulith `verify()` 保证。详见根 `docs/services/application-service/architecture.md`。

## 本地启动

先起依赖库（该目录自带 Compose，只启动 PostgreSQL，端口只绑 `127.0.0.1:5432`）：

```powershell
Copy-Item .env.example .env    # 修改 POSTGRES_PASSWORD
docker compose up -d
```

再注入必填变量并启动（缺失即启动失败，属设计行为）：

```powershell
# JWT 密钥对（仅首次；生产私钥请放密钥管理）
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out jwt-private.pem
openssl rsa -in jwt-private.pem -pubout -out jwt-public.pem

$env:DB_PASSWORD="与 .env 一致"
$env:JWT_PRIVATE_KEY=(Get-Content jwt-private.pem -Raw)
$env:JWT_PUBLIC_KEY=(Get-Content jwt-public.pem -Raw)
$env:AUTH_ADMIN_PASSWORD="本地登录口令"
.\mvnw.cmd spring-boot:run
```

```bash
DB_PASSWORD=xxx \
JWT_PRIVATE_KEY="$(cat jwt-private.pem)" \
JWT_PUBLIC_KEY="$(cat jwt-public.pem)" \
AUTH_ADMIN_PASSWORD=xxx ./mvnw spring-boot:run
```

- 默认 profile 为 `local`（`application.yaml` 的 `spring.profiles.default`）；可选 `dev`、`prod`、`test`。
- 端口使用 Spring Boot 默认 **8080**，`application*.yaml` 未显式配置 `server.port`。
- 数据库：`local` 默认 `jdbc:postgresql://localhost:5432/agent`；`prod` 无默认值，`DB_URL` 必须显式提供。
- 引导账号由 `BootstrapUserSeeder` 在 Flyway 建表后播种；`AUTH_ADMIN_PASSWORD` 留空则不创建该账号（`demo` 同理）。
- 模型运行时默认关闭（`MODEL_RUNTIME_ENABLED=false`、`BYOK_ENABLED=false`）。关闭时 `/internal/v1/**`、`/api/v1/models`、模型连接与用量接口统一返回 404（`ModelRuntimeGuard`），不是 403/503。
- 全部环境变量及生产 fail-fast 规则只查根 [`docs/deployment/environment-variables.md`](../docs/deployment/environment-variables.md)，本文件不复制变量表。

启动后可访问 `/actuator/health`、`/actuator/info`、`/swagger-ui.html`、`/v3/api-docs`（`prod` 关闭接口文档）。首次启动时 Flyway 依次执行 V1–V17 迁移（V1 为基线，V2 起建表）。

本地库在远端、需要联调时，用 SSH 隧道把远端数据库端口映射到本机再连（仓库中没有现成的隧道命令，具体方案**待确认**）；无论何种方式都禁止把数据库端口暴露到公网。部署相关步骤见根 [`docs/deployment/deployment-guide.md`](../docs/deployment/deployment-guide.md)。

## 常用命令

| 命令 | 说明 |
| --- | --- |
| `.\mvnw.cmd spring-boot:run` | 本地启动（默认 `local` profile） |
| `.\mvnw.cmd verify` | 编译 + 全部测试 + JaCoCo 报告，提交前必须通过 |
| `.\mvnw.cmd -o verify` | 离线模式执行同一门禁 |
| `.\mvnw.cmd -q verify` | 静默模式，CI / 提交前推荐 |

- `verify` 会执行全部单测与集成测试；持久层测试通过 Testcontainers 启动真实 PostgreSQL，本机需 Docker 可用。
- 覆盖率报告生成在 `target/site/jacoco`。当前 `pom.xml` 只生成报告、未配置 `check` 阈值，因此不会因覆盖率阻断构建。
- 远端推送前禁止使用 `-DskipTests`。生产 profile 的启动守卫（`ProdConfigGuard`）见根 `docs/services/application-service/security.md`。

## 文档入口

| 文档 | 内容 |
| --- | --- |
| [`docs/services/application-service/architecture.md`](../docs/services/application-service/architecture.md) | 模块、分层、请求链路、数据访问、测试结构、已知问题 |
| [`docs/services/application-service/api-reference.md`](../docs/services/application-service/api-reference.md) | 端点清单、DTO、错误码、内部接口（Agent → Java） |
| [`docs/services/application-service/security.md`](../docs/services/application-service/security.md) | RS256 签发与校验、刷新会话与 Cookie、过滤链、来源校验、CORS、生产守卫 |
| [`docs/services/application-service/development-guide.md`](../docs/services/application-service/development-guide.md) | profile、分层落位、新增接口与模块、Flyway V1–V17、测试与门禁 |
| [`docs/api-contract.md`](../docs/api-contract.md) | 三端公共契约（路径前缀、信封、SSE、跨端对照） |
| [`docs/deployment/environment-variables.md`](../docs/deployment/environment-variables.md) | 环境变量权威表与生产 fail-fast 清单 |
| [`docs/model-runtime-architecture.md`](../docs/model-runtime-architecture.md) | 模型接入与调度设计（控制面 / 数据面 / 凭证通道） |

## 注意

- 除管理端外的接口均已实现；`/api/v1/admin/**` 仍为**规划中，未实现**（仓库内无任何 `Admin*Controller`，该路径目前只有 `ADMIN` 授权规则）。
- 本服务不调用 Agent：全仓无 `WebClient` / `RestTemplate` / `RestClient` / Feign。调用方向是 Agent → Java 的 `/internal/v1/**`（服务令牌 + `X-User-Token`），见 `api-reference.md` §8。
- 生产环境 `spring.profiles.active=prod` 会触发 `ProdConfigGuard`，`debug=true`、JWT 密钥缺失或不成对、数据库口令为占位值等一律拒绝启动，不要试图绕过。
