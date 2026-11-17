# Application Service 架构

| 项 | 内容 |
| --- | --- |
| 适用范围 | `application-service/` 的模块划分、分层、数据访问、迁移与 PC 配置模块 |
| 状态 | Current |
| 最后更新 | 2026-11-17 |
| 权威性 | 本文是 Java 服务级事实源；接口字段见 [api-reference.md](./api-reference.md)，契约见 [api-contract.md](../../api-contract.md) |
| 主要证据 | `src/main/java/com/example/agent/**`、`src/main/resources/db/migration/**`、`application-*.yaml` |

## 1. 结论先行

- Java 21 + Spring Boot；按业务域分包，每域内分 `application` / `domain` / `infrastructure` / `web`。
- Java 是 JWT 唯一签发方，也是 PC 配置的事实权威。
- PC 配置已取消「求解器选型」：只有 `compose`、`validate`、`validate-partial` 与快照读取；不提供求解端点。
- 兼容规则 9 条集中在 `pcbuild/domain`，状态 `PASS` / `WARNING` / `FAIL` / `UNKNOWN`。
- Flyway 管理 Schema；当前最高版本 `V26`。

## 2. 模块

| 包 | 职责 | 关键类 |
| --- | --- | --- |
| `identity` | 注册、登录、刷新、登出、用户资料、管理员用户管理、审计 | `AuthController`、`RefreshSessionService`、`JwtTokenService`、`AdminUserService` |
| `model` | 模型目录、平台模型、BYOK 凭证、运行时任务、额度、定价、对账 | `ModelCatalogService`、`ModelRuntimeService`、`CredentialCipher` |
| `pcbuild` | 硬件目录、跑分、报价、兼容、组装、快照 | `PcBuildInternalController`、`PcHardwareInternalController`、`BuildSolveService`、`CompatibilityValidator` |
| `feedback` | 消息反馈 | `MessageFeedbackService` |
| `shared` | 响应封装、错误码、安全、MyBatis、配置 | `ApiResponse`、`GlobalExceptionHandler`、`JwtAuthenticationFilter` |

## 3. 分层

| 层 | 职责 | 约束 |
| --- | --- | --- |
| `web` | 路由、参数校验、响应封装 | 不写业务规则 |
| `application` | 用例编排、事务边界 | 一个用例一个方法；跨域调用走服务接口 |
| `domain` | 实体、值对象、规则、状态机 | 不依赖 Spring Web / MyBatis |
| `infrastructure` | Repository、外部客户端、加密 | SQL 参数化；外部调用设超时 |

依赖方向：`web → application → domain`，`infrastructure` 实现 `domain` / `application` 定义的端口。

## 4. 数据访问与事务

- MyBatis + 参数化 SQL；禁止字符串拼接用户输入。
- 写操作在 `application` 层加事务；快照写入必须与组装结果一致。
- 列表分页；常用过滤/排序列建索引；禁止 `SELECT *`。
- 资源按 `user_id` 过滤；越权与不存在返回同一错误码，避免枚举。
- 内部接口不落用户会话，只做事实计算；`compose` 落 append-only 快照。

## 5. 安全

- JWT：RS256，Java 持私钥；Access Token 短时效，Refresh Token 为不透明随机串，经 `HttpOnly` Cookie。
- 刷新令牌轮换 + 宽限期；重放检测可撤销整族。
- 内部接口：`token_use=service`；用户维度额外校验 `X-User-Token` 的 `sub`。
- 管理员接口校验 `ADMIN` 角色；审计写入 `auth_audit_logs`。
- 生产 `ProdConfigGuard` 校验 profile、Cookie `Secure`、管理员口令、JWT 密钥与占位符。

细节见 [security.md](./security.md)。

## 6. Flyway

| 版本 | 内容 |
| --- | --- |
| `V1`–`V6` | 基线、用户、刷新会话、资料、偏好、审计 |
| `V7`–`V23` | 模型目录、运行时任务、用量、配额、凭证、定价、BYOK provider、推理能力 |
| `V24` | `pc_build_snapshots` |
| `V25` | 消息反馈 |
| `V26` | DeepSeek 模型展示名 |

规则：迁移只追加，不回改已发布脚本；生产启动自动执行，失败即拒绝启动。

## 7. PC 配置模块

### 7.1 端点

| 端点 | 用途 | 落库 |
| --- | --- | --- |
| `GET /internal/v1/pc/hardware/candidates` | 候选硬件 | 否 |
| `GET /internal/v1/pc/hardware/{hardwareId}` | 硬件详情 | 否 |
| `GET /internal/v1/pc/benchmarks` | 跑分 | 否 |
| `GET /internal/v1/pc/offers` | 报价 | 否 |
| `POST /internal/v1/pc/builds/validate` | 完整兼容校验 | 否 |
| `POST /internal/v1/pc/builds/validate-partial` | 部分兼容校验 | 否 |
| `POST /internal/v1/pc/builds/compose` | 取价、组装、预算、兼容、快照 | 是 |
| `GET /internal/v1/pc/builds/{buildId}` | 快照回读 | 否 |

**不提供**求解端点。旧求解器搜索逻辑已删除，相关类只保留最低有效报价聚合与草稿组装两个事实辅助方法。

### 7.2 组装时序

```text
loadCatalog(catalogVersion)
  → requireRequirements()
  → resolveLowestOffers()        最低有效报价，缺报价 → 40307
  → CompatibilityValidator.validate()  9 条规则
  → assertNoFailure()            FAIL → 40308
  → assertWithinBudget()         超预算 → 40309
  → BuildResultFactory          快照与响应
  → BuildSnapshotService.insert()  仅成功路径
```

失败不落库；`UNKNOWN` 不阻止组装，但会随报告返回。

### 7.3 兼容规则

9 条规则、判定字段与 `UNKNOWN` 语义只在 [compatibility-rules.md](../../pc-config/compatibility-rules.md) 维护。`CompatibilityValidator` 的 Javadoc 仍保留旧条数标注，以代码常量与本文档的 9 条为准。

### 7.4 数据来源

- 运行时读取 `classpath:pc-config/{catalog,benchmarks,offers}.json`，启动期缓存。
- 目录 402 款；报价 402 条全部 `PLATFORM_OBSERVED`；跑分 169 条。
- 详见 [data.md](../../pc-config/data.md)。

## 8. 已知边界

- 报价只读夹具，无报价表、无自动采集与过期清理。
- 离线治理主数据未接入运行时。
- 管理端无硬件/报价维护页。
- 快照 `parent_build_id` 预留未写入；无保留期与归档任务。
- 多方案对比、交互式换件【未实现】。

## 9. 相关文档

- 接口：[api-reference.md](./api-reference.md)
- 安全：[security.md](./security.md)
- 开发规范：[development-guide.md](./development-guide.md)
- PC 兼容：[compatibility-rules.md](../../pc-config/compatibility-rules.md)
- 总体架构：[architecture-overview.md](../../architecture-overview.md)
