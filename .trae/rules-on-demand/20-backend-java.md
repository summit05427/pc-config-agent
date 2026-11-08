---
alwaysApply: true
---

# Java 后端规则（application-service/**）

适用范围：仅 `application-service/**`。其他目录忽略本文件；公共约束见 `00-monorepo-common.md`。

## 1. 技术基线

Java 21 + Spring Boot 4.1（Spring Framework 7）+ Maven Wrapper + PostgreSQL（MyBatis 3.5）+ Flyway + Spring Security 7（OAuth2 Resource Server + RS256 JWT，无状态）+ JUnit 5，基础包 `com.example.agent`。

- **强制**：违反即缺陷，评审打回；**建议**：偏离需在 PR 中说明。
- 与公共规则冲突时以本文件为准，未覆盖部分沿用公共规则。

## 2. 分层与命名

依赖方向固定 `controller → service → repository`，禁止反向依赖与跨层调用（Controller 不直接调 Repository）。

Spring Modulith 模块：`identity`（用户与令牌）、`model`（模型运行时控制面：目录 / BYOK 凭证 / 额度 / 用量）、`shared`（信封、异常、请求上下文）。模块之间只经公开 API，禁止直插对方内部包。

阅读顺序：[docs/README.md](../../docs/README.md) → `docs/services/application-service/{architecture,security,api-reference}.md`；跨端改动先读 `docs/api-contract.md`。

| 包 | 职责 | 禁止放入 |
| --- | --- | --- |
| `controller` | 参数接收、校验、调用 service、组装响应 | 事务、SQL、业务分支 |
| `service` | 业务编排、事务边界、领域规则 | HTTP 对象、Servlet API |
| `repository` / `mapper` | 数据访问 | 业务判断、事务控制 |
| `domain` | 实体、值对象、领域枚举 | 对外传输结构 |
| `dto` | 请求/响应对象，按 `request`、`response` 分包 | 持久化注解、业务方法 |
| `config` / `exception` / `security` / `common` | 配置装配、异常处理、认证鉴权、通用基础 | 具体业务流程 |

命名：包全小写无分隔；类 PascalCase 带语义后缀（`MatchController`、`MatchService`）；方法与变量 camelCase 动词开头；常量 SCREAMING_SNAKE_CASE；DTO 为「用途 + 方向」（`MatchCreateRequest`）；测试类为「被测类名 + Tests」。禁止无意义缩写与单字母变量（循环计数除外），布尔值用 `is` / `has` / `can` 前缀。

## 3. 编码约定

- 4 空格缩进、UTF-8、LF，行宽不超过 120；方法不超过 50 行、嵌套不超过 3 层（建议类不超过 500 行）。
- 禁止 `System.out` / `System.err` / `printStackTrace()`、注释掉的代码块与调试残留。
- 构造器注入 + `@RequiredArgsConstructor` + `private final`，禁止 `@Autowired` 字段注入；日志用 `@Slf4j`。
- 实体与对外 DTO 禁用 `@Data`，改用 `@Getter` / `@Setter` / `@Builder` 等显式声明。
- 对外方法不返回 `null` 集合（返回空集合）；`Optional` 仅作返回值；时间用 `java.time`（存储 UTC）；金额、比率用 `BigDecimal`；不可变数据载体优先 `record`。
- 字符串比较用 `Objects.equals` 或常量在左；魔法值提取为常量或枚举。
- 业务失败统一抛 `BusinessException`（携带错误码）；禁止空 `catch`、禁止捕获 `Throwable`，捕获 `Exception` 仅限边界层并说明原因。

## 4. API 设计

- 前缀 `/api/v1`，资源名复数 kebab-case，禁止动词化路径；`GET` 查询、`POST` 创建、`PUT` 全量更新、`PATCH` 局部更新、`DELETE` 删除；嵌套不超过两级。
- 请求体与响应体必须是显式 DTO，禁止 `Map` / `JSONObject` / `JsonNode` 承载业务字段。
- 入参用 `@Valid` 校验 DTO；`@RequestParam`、`@PathVariable` 直接在参数上声明约束。禁止在 Controller 类上加 `@Validated`，避免退化为 AOP 校验。
- 统一响应 `{code, message, data, requestId}`：`code` 为业务码（成功固定 `0`），HTTP 状态码表达协议语义，`requestId` 与 `X-Request-Id` 一致，`data` 为空时不输出。
- 列表响应含 `list`、`total`、`page`、`size`；默认 `page=1`、`size=20`，服务端强制 `size ≤ 100`，超限返回 400。
- 时间字段统一 ISO-8601（`2026-10-22T08:00:00Z`）；响应与 URL 中禁止出现密码、token 等敏感信息。
- 错误码区间：`0` 成功、`1xxxx` 通用请求、`2xxxx` 认证权限、`3xxxx` 资源与通用业务、`4xxxx` 业务模块、`5xxxx` 服务端。错误码枚举实现 `ErrorCode`（业务码 + HTTP 状态 + 面向调用方的消息），全局唯一并登记。
- 全局异常由 `@RestControllerAdvice` 覆盖参数校验、业务异常、未预期异常；对外不输出堆栈、SQL、表名、类名与服务器路径，未预期异常返回 500 + traceId 并只记录一次堆栈。
- 建议：创建接口支持 `Idempotency-Key`，写接口用乐观锁或唯一约束兜底并发；破坏性变更新增 `/api/v2`。
- 内部接口 `/internal/v1/**`：只接受服务令牌（`token_use=service`），不经 Nginx 暴露；用户维度端点必须同时校验 `X-User-Token` 的归属，不得用服务令牌直接操作任意用户数据。契约见 `docs/api-contract.md` §5.6。

## 5. 事务与数据访问

- `@Transactional` 只标在 service 层 public 方法，禁止标在 Controller、Repository、私有或自调用方法；查询标 `readOnly = true`。
- 事务内禁止调用外部 HTTP、发送消息、执行耗时计算；异常须为运行时异常或显式 `rollbackFor`，通知与缓存刷新放到提交后。
- SQL 全部参数化（`#{}` 或 `?`），禁止字符串拼接与 `${}` 拼接用户输入；禁止 `SELECT *`，字段显式列出。
- 过滤列、排序列必须建索引；禁止在索引列上使用函数或隐式类型转换。
- 列表在数据库侧分页；批量写入用批量语句；禁止循环内查询（N+1），用关联或批量查询替代。
- DDL 与初始化数据全部走 Flyway 版本脚本，禁止手工改库；已合入主干的脚本只可追加不可修改；结构变更遵循「先扩展、后收缩」；生产禁止无 `WHERE` 的 `UPDATE` / `DELETE`。

## 6. 配置与生产守卫

- 配置放 `application.yaml`，按环境拆 `application-{profile}.yaml`，默认 profile 不得指向生产。
- 密钥、口令、连接串凭据只从环境变量注入，禁止硬编码、禁止提交真实 `.env` 或生产配置。
- 配置项 kebab-case 命名，同前缀集中管理；优先 `@ConfigurationProperties`，禁止多处散落 `@Value`。
- 日志级别、连接池、超时必须显式配置；禁止硬编码服务地址、端口与第三方域名。
- `ProdConfigGuard` 不得删除或绕过：`spring.profiles.active=prod` 时，`debug=true`、JWT 私钥/公钥缺失或不成对、默认占位口令必须直接阻止启动。

## 7. 日志与可观测

- 用 SLF4J 占位符 `{}`，禁止字符串拼接；日志含业务主键、操作类型、traceId。
- `ERROR` 仅用于需人工介入的故障，`WARN` 用于可恢复异常与降级，`INFO` 记录关键节点，`DEBUG` 不进生产默认级别；同一异常只打印一次堆栈。
- 禁止打印密码、token、身份证号、手机号、银行卡号等敏感字段。
- Actuator 仅暴露 `health` 与 `info`，生产禁止暴露 `env`、`heapdump`、`threaddump`。

## 8. 安全

- 认证鉴权在过滤器或拦截器统一处理，Controller 内不重复判权；按 ID 访问资源必须校验数据归属。
- JWT 使用 RS256（私钥签发），校验 issuer 与 aud；Token 只由本服务签发，Agent 只持公钥验签。
- JWT `sub` 必须是 `users.public_id`（UUID），禁止写入内部自增主键或登录名。
- 唯一豁免：服务令牌（`token_use=service`）的 `sub` 是服务客户端标识（默认 `agent-service`），由 `ServiceTokenService` 签发，只带 scope，只能访问 `/internal/v1/**`，不得访问用户接口；签发与校验两侧都不得把它当作用户身份。
- 输入校验以服务端为准（DTO 声明长度、格式、范围、枚举），禁止只依赖前端。
- 禁止拼接 SQL；禁止用 `Runtime.exec` / `ProcessBuilder` 拼接用户输入执行命令。
- 文件上传校验类型白名单、大小上限与内容嗅探，文件名不信任用户输入，存储与代码隔离。
- 密码用 BCrypt 或 Argon2，禁止明文与可逆加密；CORS 用明确白名单，禁止 `*` 与 `allowCredentials` 同时开启。
- 响应与日志不出现密钥、token 与完整个人敏感信息，必要时脱敏。
- 建议：新依赖评估许可证与漏洞并定期扫描；对外接口按调用方限流。

## 9. 测试与门禁

- 单测用 JUnit 5 且不启容器，外部依赖用 Mockito 隔离；集成测试用 `@SpringBootTest`，数据库相关优先 Testcontainers。
- 测试方法名表达「场景 + 预期」；每个业务分支覆盖成功、参数非法、资源不存在、无权限。
- 禁止长期保留 `@Disabled`（需注明原因与恢复条件）；禁止降低断言强度或删除断言换取通过。
- 提交前必须执行：Windows `cd application-service; .\mvnw.cmd -q verify`，Linux/macOS `cd application-service && ./mvnw -q verify`；禁止用 `-DskipTests` 推远端。
- 核心 service 覆盖率 ≥ 70%（建议），JaCoCo 报告随 CI 归档。

## 10. Monorepo 集成

- 容器内端口 `8080`，服务名 `application-service`；数据库用 `postgres:5432/agent`。
- Java 与 Agent 共享 `JWT_PUBLIC_KEY`、`JWT_KID`、`JWT_ISSUER`、`JWT_AUDIENCE`，issuer 固定为 `agent-application-service`；私钥只注入 Java，修改任一方必须同步根 `.env`。
- 前端经 Nginx `/api/` 访问本服务；后端不感知前端域名，不在代码中写死。
- 修改 API 契约时同步前端类型、Agent Schema 与根 `docs/`。

## 11. 版本与发布

- 语义化版本 `MAJOR.MINOR.PATCH`，标签 `v1.2.3`；发布顺序 开发 → 预发 → 生产，禁止跳预发。
- 产物为可执行 JAR，`devtools` 不得进入生产；每次发布保留上一版本产物与配置，支持 10 分钟内回滚；数据库变更必须向前兼容。
- 接口与配置变更同步更新根 `docs/`；复杂流程（状态机、异步补偿、批量任务）写设计说明。
- 公共类与方法写 Javadoc（参数、返回值、异常、副作用）。

## 12. AI 编码防错清单（建议）

- **大范围删除/替换**：单次 `old_string` 不超过 30 行，首尾各留一个唯一锚点；涉及字段块、类尾部时拆成多次编辑。改完立即编译，禁止连续堆叠多处未验证的编辑。
- **改签名后先找调用点**：修改构造器、方法签名或依赖注入类型后，先 `Grep` 全部构造与调用点（含 `src/test`、`InMemory*`、配置装配类），再改实现。
- **删 import 前先确认引用**：用 `Grep` 查该类型在文件内的实际使用；无法确认就保留，让编译器裁决，禁止凭印象批量删除。
- **数字必须可追溯**：文档与结论中的类数量、调用方数量、覆盖率只能来自命令输出或测试报告；未核实就写「未核实」，禁止估算。
- **判定重复前先核对语义**：合并前比对调用方与行为差异；语义不同的「重复」记录理由后关闭，不为对称强行合并。
- **重构默认零行为变化**：错误码、响应字段、日志级别、启动失败时机需要变化时，必须单列说明并取得确认。
- **提交粒度**：按「新增模块 → 双路径委托 → 删除旧实现 → 补齐文档」拆分，每个提交独立可编译且 `verify` 通过。
