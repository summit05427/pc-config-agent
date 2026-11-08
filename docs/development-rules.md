# 跨端开发与文档维护规则

| 项 | 内容 |
| --- | --- |
| 状态 | Current |
| 最后核验 | 2026-11-01 |
| 权威性 | Authoritative（跨端变更流程、影响矩阵、门禁命令） |
| 主要证据 | `frontend/package.json`、`admin/package.json`、`application-service/pom.xml`、`agent-service/pyproject.toml`、`frontend/deploy/nginx/default.conf.template`、`.github/workflows/ci.yml` |

适用范围：整个仓库。本文只约束「改动跨端契约时做什么、验证什么、同步哪些文档」。代码风格与硬约束见 `.trae/rules/`（入口 [rules/00-monorepo-common.md](../.trae/rules/00-monorepo-common.md)）；服务规则在 `.trae/rules-on-demand/`，改动对应目录前按路由表读取，不在此重复。

> 2026-11-01 修订：删除内嵌的历史测试数字快照（会随代码过期，且易被误读为当前结果）；补齐 Agent → Java 内部接口与模型运行时两类变更；部署文档路径改为 `docs/deployment/`。

## 1. 变更影响矩阵

修改任何一项时，必须按下表检查全部受影响端，不能只改当前端。

| 变更类型 | 必须检查/修改 |
| --- | --- |
| Java 接口路径、方法、DTO | `application-service/**/controller/**` + `dto/**` + 错误码 → `frontend/src/features/<domain>/api/` 类型与调用 → `admin/src/features/<domain>/api/` 类型与调用 → [api-contract.md](api-contract.md) §5 → [services/application-service/api-reference.md](services/application-service/api-reference.md) |
| 管理端页面、search 参数、筛选与分页 | `admin/src/routes/**` + `admin/src/features/<domain>/**` → [services/admin/architecture.md](services/admin/architecture.md) → [services/admin/development-guide.md](services/admin/development-guide.md) |
| Java 鉴权、JWT claims、issuer、密钥 | `application-service/**/security/**` → `agent-service/app/core/security.py` + `AUTH__*` 配置 → 根 `.env.example` 与 `agent-service/.env.example` → [architecture-overview.md](architecture-overview.md) §4 → [services/application-service/security.md](services/application-service/security.md) → [deployment/environment-variables.md](deployment/environment-variables.md) |
| 刷新令牌、Cookie 名/属性/期限 | `RefreshSessionService` / `RefreshCookieFactory` / `RequestOriginValidator` → `frontend/src/core/http/auth.ts` + `frontend/src/features/auth/model/auth-session.ts`（依赖 Cookie 恢复）+ `admin/src/core/http/client.ts` + `admin/src/stores/auth-store.ts` → [api-contract.md](api-contract.md) §2、§5 → [services/application-service/security.md](services/application-service/security.md) → `AUTH_REFRESH_*` / `AUTH_COOKIE_SECURE` 两份 `.env.example` → [deployment/environment-variables.md](deployment/environment-variables.md) |
| 前端登录态、401/403 处理 | `frontend/src/core/http/{auth,httpJson,sseStream}.ts` + `frontend/src/features/auth/model/auth-session.ts` + `frontend/src/routes/{guards,router}.ts` + `frontend/src/main.tsx`（装配刷新与跳转） → [services/frontend/architecture.md](services/frontend/architecture.md) → [api-contract.md](api-contract.md) §2 |
| Agent 接口路径或字段 | `agent-service/app/api/v1/**` + Pydantic Schema → `frontend/src/features/sessions/api/{sessions,stream-chat,types}.ts` → [api-contract.md](api-contract.md) §6 → [services/agent-service/api-reference.md](services/agent-service/api-reference.md) |
| SSE 事件类型、字段、结束语义 | `agent-service/app/api/v1/chat.py` + `sse.py` → `frontend/src/features/sessions/api/stream-chat.ts` + `frontend/src/core/http/sseStream.ts` + `frontend/src/features/chat/runtime/agent-runtime.ts` → [api-contract.md](api-contract.md) §7 → 两端文档 |
| Agent 历史消息存储结构 | `agent-service/app/services/session_store/`（表结构、窗口查询）→ [api-contract.md](api-contract.md) §6 → `docs/services/agent-service/{api-reference,architecture,agent-workflows}.md` |
| Agent 错误码 | `agent-service/app/core/exceptions.py` 与各 `AppError` 调用点 → 前端 `error` 事件处理 → [api-contract.md](api-contract.md) §8 |
| **Agent → Java 内部接口**（`/internal/v1/**`） | `application-service/**/controller/**`（internal 路由）+ `ServiceTokenService` → `agent-service/app/services/{control_plane,model_resolver,model_runtime,model_usage}.py` → [api-contract.md](api-contract.md) §5.6 → [services/application-service/api-reference.md](services/application-service/api-reference.md) §8 → `INTERNAL_AUTH__*` 两份 `.env.example` |
| **模型运行时**（Provider / 模型目录 / BYOK / 额度） | `application-service/**/model/**` + Flyway V7–V17 → `agent-service/app/services/{model_resolver,model_runtime,llm}.py` + `frontend/src/features/models/api/`、`features/usage/api/` → [api-contract.md](api-contract.md) §5.2–§5.4 → [model-runtime-architecture.md](model-runtime-architecture.md) → [services/application-service/api-reference.md](services/application-service/api-reference.md) |
| 新增/修改环境变量 | 对应服务的 `.env.example` → 根 `.env.example` → `docker-compose.yml` / `deploy/docker-compose.infra.yml` 注入 → [deployment/environment-variables.md](deployment/environment-variables.md) → [deployment/deployment-guide.md](deployment/deployment-guide.md)（若影响启动步骤） |
| 修改 Nginx 路由或超时 | `frontend/deploy/nginx/default.conf.template` → 前端 `VITE_*` 默认值（`frontend/src/shared/lib/env.ts`）→ [api-contract.md](api-contract.md) §1 → [architecture-overview.md](architecture-overview.md) §2 |
| 修改数据库 schema | 只能通过 Flyway（Java）或 `STORAGE__AUTO_SETUP` 建表脚本（Agent）→ 服务文档的数据归属章节 → 不得跨库读写 |
| 修改 UI Token、控件尺寸 | [services/frontend/ui-design-system.md](services/frontend/ui-design-system.md) → 前端样式实现；两者必须同时改 |
| 升级依赖版本 | 服务文档的技术栈与版本行 → 验证命令实测通过后才可提交 |

判断依据：只要一条信息同时出现在两个端的代码里（路径、字段名、错误码、事件名、环境变量名），它属于跨端契约，必须按上表同步。

## 2. 唯一的权威来源

修改前先确认「这条事实归谁写」，只改权威文档，其他位置只保留链接：

| 事实 | 唯一权威 |
| --- | --- |
| 跨端路径、字段、错误码、SSE 事件、内部接口 | [api-contract.md](api-contract.md) |
| 系统职责（含管理端）、拓扑、数据归属、未实现清单 | [architecture-overview.md](architecture-overview.md) |
| 环境变量名、默认值、生产守卫 | 两份 `.env.example` + [deployment/environment-variables.md](deployment/environment-variables.md) |
| 部署与上线步骤 | [deployment/deployment-guide.md](deployment/deployment-guide.md) |
| 认证与令牌细节 | [services/application-service/security.md](services/application-service/security.md) |
| 端点签名细节（DTO 字段、校验、错误码） | 各服务 `docs/services/<service>/api-reference.md` |
| 管理端结构、认证流程、页面能力 | [services/admin/architecture.md](services/admin/architecture.md) |
| 模型运行时设计决策 | [model-runtime-architecture.md](model-runtime-architecture.md) |
| 编码硬约束 | `.trae/rules/*.md` |
| 未完成事项与优先级 | [planning/closure-plan.md](planning/closure-plan.md) |
| 文档分类、状态标签、命名与归档 | [documentation-governance.md](documentation-governance.md) |

- 三端公共契约只写在根 `docs/`；服务内 `docs/` 不提交（`.gitignore` 已排除），不得在其内维护第二份契约。
- 服务 `README.md` 只描述启动、验证与文档入口，不重复契约细节。

## 3. 兼容性规则

- **兼容性变更**：新增可选字段、新增事件类型、新增端点、放宽校验。旧客户端必须仍可工作；前端必须忽略未知事件与未知字段。
- **破坏性变更**：删除或改名路径/字段、修改字段语义、修改错误码含义、修改 SSE 结束语义、修改鉴权方式。必须新增 `/api/v2`，不允许原地替换。
- **不兼容的默认值变更**（如分页默认 `size`）按兼容性变更处理，但要在 `api-contract.md` 中注明。
- 数据库变更必须向前兼容：先扩展（加列/加表），发布后再收缩（删旧列），禁止同一次发布内破坏旧版本读写。

## 4. 验证要求与命令

提交前按改动范围执行。前端命令在 `frontend/` 目录内执行，统一用 `corepack pnpm` 固定 pnpm 版本。

```powershell
# 前端（cwd frontend）
corepack pnpm lint:ci        # oxlint + eslint，只检查不改文件
corepack pnpm type-check     # tsc -b
corepack pnpm test           # Vitest
corepack pnpm test:coverage  # 行覆盖率门槛 80%
corepack pnpm e2e:critical   # Playwright --grep @critical

# 管理端（cwd 仓库根）
corepack pnpm --dir admin lint:ci
corepack pnpm --dir admin type-check
corepack pnpm --dir admin test
corepack pnpm --dir admin build

# Java
cd application-service; .\mvnw.cmd -q verify

# Agent
uv --directory agent-service run ruff check app tests evals run.py
uv --directory agent-service run mypy
uv --directory agent-service run pytest -q --cov=app --cov-report=term-missing
uv --directory agent-service run python -m evals --fake

# 部署编排
docker compose --env-file .env config -q

# 文档链接、环境变量键一致性与迁移门禁
powershell -File scripts/check-doc-links.ps1
powershell -File scripts/check-env-docs.ps1
powershell -File scripts/check-migrations.ps1
```

结果记录要求：

- 只记录**实际执行过**的结果；未执行写「未执行」，失败写真实数字与原因。
- 禁止用 `skip`、`@Disabled`、`-DskipTests` 或降低断言换取通过。
- 一次性测试快照写进 `docs/quality/` 的报告，而不是写进本文；本文只保留命令与门槛，避免数字随代码过期后误导读者。

## 5. 评审清单

评审跨端改动时至少确认：

1. 路径前缀与 Nginx 转发是否匹配（`/api/` 保留、`/agent/` 剥前缀）。
2. 请求/响应字段类型、可空性、默认值是否在两端一致。
3. 鉴权是否仍在服务端完成；是否出现按 ID 访问未校验归属。
4. 内部接口是否只允许服务令牌访问 `/internal/v1/**`；用户维度调用是否同时校验 `X-User-Token` 的归属。
5. 管理端是否只调用 `/api/v1/admin/**` 与 `/api/v1/auth/**`，访问令牌是否仍只存内存。
6. 错误码是否落在既定区间/命名空间，HTTP 状态是否与语义一致。
7. SSE 是否保持 `done` 收尾、未知事件可忽略、心跳可忽略、断开可取消。
8. 日志与响应是否泄露 Token、密钥、完整对话或内部堆栈。
9. SQL 是否参数化、是否在数据库侧分页、是否命中索引。
10. 文档同步是否完成（按第 1 节矩阵），`.env.example` 是否更新。
11. 是否新增未实现能力却被写成已有能力。

## 6. 文档维护规则

- 新增文档前先确认现有文档无法承载；不为每个类、目录或模块机械建档。
- 每条重要信息标注状态（已验证事实 / 已确认决策 / 待确认 / 待验证假设 / 未实现 / 历史），写法见 [README.md](README.md) §2。
- 事实必须给出证据位置（文件路径、类名、配置项），不写无法由代码或运行结果支撑的描述。
- 代码与文档冲突时：以代码为事实，把冲突登记到对应文档的「已知问题」或「待确认事项」，不擅自改代码、不擅自把某一端写成标准。
- 归档优先于删除；删除前必须确认「完全重复、无历史价值、无审计证据、无外部引用、已由权威文档完整承接」五项，并在提交信息中写清依据。
- 文档变更说明「为什么改」，不记流水账。

## 7. 阶段门禁

- 代码改动与文档改动分属不同提交，提交信息使用 `type(scope): 中文描述`。
- 涉及契约的提交必须在 PR 描述中列出：变更目的、影响端、验证命令与结果、回滚方式。
- 未验证的能力不得写入文档；未实现的接口不得出现在契约表中，或必须显式标记【未实现】。

## 8. AI 编码守则（强制）

以下条款来自已发生的返工，不是假设：

1. **证据先于结论**：改代码前先读实现与测试；无法从代码确认的事实写「无法确认」，不补脑补逻辑。报告或清单里没有的候选，不擅自扩展范围。
2. **公共签名优先**：重构保持导出函数与组件 props 不变；必须改签名时先说明影响面并单独提交迁移。
3. **格式不动**：持久化键名、前缀、结构与序列化格式属于外部契约（`index.html` 首屏脚本、兼容回读都可能依赖），内部实现重写不得改动它们。
4. **测试确定性**：单测不得依赖本机 `.env.local`、时区、真实网络；涉及地址与开关的用例显式 mock 配置。E2E mock 按 `URL.pathname` 归一化前缀，通配覆盖全部版本段。
5. **全量验证**：重构或改测试替身后必须跑全量测试与关键 E2E，不能只跑改动文件的 spec；门禁失败先定位根因，不靠放宽断言或跳过用例通过。
6. **断言稳定**：优先语义元素与路由状态，不绑易变文案；删除文件前先全局搜索引用，确认无调用方再删。
7. **一次只做一件事**：提交按模块拆分，不把格式化、重命名、无关修复混入同一提交。
8. **重复规则先收口**：同一套校验、编解码或坏值处理出现第二份时，先抽共享模块再改行为；合并时保留对外可观测的错误文案与日志事件名。
9. **生命周期成对**：请求级状态用单一上下文管理器进入/退出，禁止成对的 `start_*` / `reset_*`，避免异常路径只复位一半。
10. **编排不进路由**：路由只做传输与协议编码；多步装配、回合编排与持久化分别落在服务层模块，便于单测与替换实现。
