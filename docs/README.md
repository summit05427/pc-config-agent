# 文档地图（唯一导航入口）

| 项 | 内容 |
| --- | --- |
| 状态 | Current |
| 最后核验 | 2026-11-05 |
| 权威性 | Authoritative（本文件是文档全量清单；按任务的最小阅读路径见 [INDEX.md](INDEX.md)） |

仓库内只有根 `docs/` 是各端公共契约的权威来源。`frontend/docs/`、`application-service/docs/` 已被 `.gitignore` 排除，`agent-service/docs/` 不存在；这三者都不构成权威文档。

**冲突优先级（唯一规则）**：代码 > `.env.example` 等可执行配置 > 本仓库权威文档 > 历史归档。

`.trae/rules/` 是编码硬约束，与 `docs/` 冲突时以能通过 CI 的可执行配置为准，并同时修正规则或文档；不再保留「docs 优先 / rules 优先」两套说法。

## 1. 文档清单

### 1.1 项目级与公共契约

| 文档 | 类型 | 内容 | 适用读者 |
| --- | --- | --- | --- |
| [INDEX.md](INDEX.md) | 导航（**任务路由**） | 按任务给出最小必读清单、规则文件路由与派生文档说明 | 改代码的人 |
| [architecture-overview.md](architecture-overview.md) | 事实 + 已确认决策 | 各端职责、部署拓扑、调用关系（含 Agent → Java 内部接口）、信任边界、未实现能力 | 所有人 |
| [api-contract.md](api-contract.md) | 契约 | 路径前缀、鉴权、双响应信封、Java/Agent/内部接口、SSE 协议、错误码总表 | 改接口的人 |
| [api-contract-quick-reference.md](api-contract-quick-reference.md) | 派生速查 | API 契约速查视图（源：`api-contract.md`） | 改接口的人 |
| [design-system/cross-app-ui-contract.md](design-system/cross-app-ui-contract.md) | 契约（跨端 UI） | L0 品牌层与 L1 语义层的唯一权威：品牌色、语义状态映射、两端对齐规则 | 改前端 / 管理端 UI 的人 |
| [development-rules.md](development-rules.md) | 规范 | 跨端变更影响矩阵、兼容性、验证命令、评审清单 | 提交代码的人 |
| [documentation-governance.md](documentation-governance.md) | 规范 | 文档分类、目录与命名、状态标注、SSOT、变更与校验门禁 | 写文档的人 |
| [model-runtime-architecture.md](model-runtime-architecture.md) | 设计 + 落地记录 | 模型接入与调度：控制面/数据面、凭证通道、PR1–PR6 状态 | 所有人 |

### 1.2 部署与运维

| 文档 | 类型 | 内容 |
| --- | --- | --- |
| [deployment/deployment-guide.md](deployment/deployment-guide.md) | 操作手册 | 环境要求、本地与全栈启动、Nginx 路由、CI job、发布与回滚、校验命令、排障 |
| [deployment/solo-mode.md](deployment/solo-mode.md) | 操作手册 | Solo 模式三条命令、dev-token、curl 流式对话、不可用能力清单 |
| [deployment/environment-variables.md](deployment/environment-variables.md) | 操作手册（**环境变量唯一权威**） | 全部环境变量、各端读取方式、生产 fail-fast、密钥生成与轮换 |
| [deployment/env-quick-reference.md](deployment/env-quick-reference.md) | 派生速查 | 环境变量速查视图（源：`environment-variables.md`） |

### 1.3 服务文档

| 文档 | 类型 | 内容 |
| --- | --- | --- |
| [services/frontend/architecture.md](services/frontend/architecture.md) | 服务事实说明 | React 分层、路由、状态归属、HTTP 门面、SSE 消费 |
| [services/frontend/ui-quick-reference.md](services/frontend/ui-quick-reference.md) | 派生速查 | UI Token 与控件速查视图（源：`ui-design-system.md`） |
| [services/frontend/development-guide.md](services/frontend/development-guide.md) | 服务规范 | 命令、目录、新增页面/接口/事件步骤、样式与门禁 |
| [services/frontend/ui-design-system.md](services/frontend/ui-design-system.md) | 服务规范 | 设计 Token、控件尺寸、组件状态、验收基线 |
| [services/frontend/generative-ui.md](services/frontend/generative-ui.md) | 服务事实说明 | OpenUI 渲染链路、组件库、状态持久化、安全边界与降级 |
| [services/application-service/architecture.md](services/application-service/architecture.md) | 服务事实说明 | Java 模块（identity/model/shared）、分层、Flyway、数据访问 |
| [services/application-service/api-reference.md](services/application-service/api-reference.md) | 服务契约 | Java 端点字段细节、错误码、内部接口实现要点 |
| [services/application-service/security.md](services/application-service/security.md) | 服务事实说明 | RS256 签发与校验、刷新会话、过滤链、来源校验、生产守卫 |
| [services/application-service/development-guide.md](services/application-service/development-guide.md) | 服务规范 | 目录、命名、事务、Flyway 与门禁 |
| [services/agent-service/architecture.md](services/agent-service/architecture.md) | 服务事实说明 | Agent 分层、生命周期、数据归属、已知问题 |
| [services/agent-service/agent-workflows.md](services/agent-service/agent-workflows.md) | 服务事实说明 | 图结构、上下文裁剪、工具治理、checkpointer、一次对话时序 |
| [services/agent-service/api-reference.md](services/agent-service/api-reference.md) | 服务契约 | Agent 端点、SSE 事件、错误码 |
| [pc-config/README.md](pc-config/README.md) | 模块文档集（**PC 配置主题入口**） | 12 份文档导航：范围、架构、工作流、状态与工具、数据模型、数据质量、报价运营、求解与兼容、接口、测试、路线图 |
| [services/admin/architecture.md](services/admin/architecture.md) | 服务事实说明 | 管理端定位、目录、认证与会话、路由守卫、页面能力、已知边界 |
| [services/admin/development-guide.md](services/admin/development-guide.md) | 服务规范 | 命令、环境变量、新增页面/接口步骤、认证改动检查、部署待接入 |

### 1.4 决策、待办与质量基线

| 目录 / 文档 | 类型 | 内容 |
| --- | --- | --- |
| [quality/enterprise-readiness.md](quality/enterprise-readiness.md) | 质量基线（**企业级达标唯一评分表**） | 六大域评分口径、逐项验收方式、P0–P2 整改 backlog、业界基准映射 |
| [adr/](adr/) | 架构决策 | 目前 10 条：`0001-frontend-direct-to-agent`、`0004-extension-config-file-first`、`0005-agent-profile-first-class`、`0006-mechanism-vs-content-boundary`、`0007-session-store-seam`、`0008-unified-model-egress-litellm`、`0009-single-pc-workflow-over-generic-chat`、`0010-deterministic-markdown-build-output`、`0011-manually-verified-offer-dataset`、`0012-persist-build-snapshot` |
| [planning/closure-plan.md](planning/closure-plan.md) | 规划（**当前待办与放行条件唯一权威**） | 已处理事项及关闭依据、未完成 P0–P3 清单、收尾执行顺序与验收标准 |
| [planning/pc-config-implementation-plan.md](planning/pc-config-implementation-plan.md) | 规划（PC 配置分期设计） | 决策 D1–D8、Stage 1–6 任务与验收指标；执行进度以本文件与 closure-plan 为准 |
| [quality/pc-config-e2e-2026-11.md](quality/pc-config-e2e-2026-11.md) | 质量证据 | Stage 5 端到端联调：三组 Demo、指标核对、基础设施回归、遗留问题 |

`docs/quality/` 现存放企业级达标评分表；`docs/archive/` 仍为空：2026-11-05 文档清理已删除全部历史归档，历史内容见 Git（清理前提交 `d4e349b`）。新增证据报告仍按 [documentation-governance.md](documentation-governance.md) §2、§10 放入对应目录。

### 1.5 历史归档（`archive/`）

`docs/archive/` 当前为空：2026-11-05 清理已删除全部历史归档（认证策略、执行计划、React 重构验收 / 审计 / 缺陷台账、Agent 模板演进报告等），历史内容见 Git（清理前提交 `d4e349b`）。归档文件只用于理解决策背景，**不得作为当前规范引用**；新增归档仍按 [documentation-governance.md](documentation-governance.md) §10 标注 `Deprecated` / `Superseded`、归档日期、废弃原因与替代文档。

当前认证权威内容见 [services/application-service/security.md](services/application-service/security.md)；环境变量权威见 [deployment/environment-variables.md](deployment/environment-variables.md)。

## 2. 信息状态标签

文档中每条重要信息都按下述状态之一表述，禁止把未验证内容写成事实。

| 标签 | 含义 |
| --- | --- |
| **已验证事实** | 有源码、配置、迁移脚本、测试或实际运行结果支撑，文中给出证据位置 |
| **已确认决策** | 项目负责人明确同意、但可能尚未全部落地 |
| **待确认事项** | 尚未决定，或需跨端协商 |
| **待验证假设** | 有依据但证据不足 |
| **未实现能力** | 设计与文档中提到，但当前代码没有实现 |
| **历史信息** | 仅解释背景，不得作为当前契约 |

写作时使用「（已验证，`路径`）」「【已确认决策】」「【未实现】」这类显式标记。

## 3. 术语

下表是跨端通用术语。前端域词汇（组件、运行时、布局等）另见根 [GLOSSARY.md](../GLOSSARY.md)。

| 术语 | 含义 | 出处 |
| --- | --- | --- |
| `thread_id`（客户端） | 前端维护的会话标识，长度 1..64；业务表以 `(user_id, thread_id)` 隔离，`thread_id` 存客户端原始值 | `agent-service/app/api/v1/chat.py`、`app/services/session_store/interface.py` |
| 检查点 / 锁的线程键 | 服务端由 `namespaced_thread_id(user, client_thread_id)` 派生，只用于 checkpointer 与分布式锁，不回传给前端 | `agent-service/app/core/security.py`、`app/api/v1/chat.py` |
| `user_id` | JWT 的 `sub`。Java 签发的 `sub` 是 `users.public_id`（UUID）；开发令牌可指定任意字符串 | `JwtTokenService.java`、`agent-service/app/api/v1/auth.py` |
| Access Token | RS256 JWT，只存前端内存，有效期 `JWT_ACCESS_TTL`（默认 `10m`） | `JwtTokenService.java`、`frontend/src/core/http/auth.ts` |
| Refresh Token | 32 字节不透明随机串，仅经 `HttpOnly` Cookie `agent_refresh` 传输；库内只存 SHA-256 摘要，闲置 7 天 / 绝对 30 天 | `RefreshSessionService.java`、`RefreshCookieFactory.java` |
| `request_id` / `requestId` | 单请求追踪标识。Agent 响应体字段为 `request_id`，Java 为 `requestId`，均来自 `X-Request-Id` | `agent-service/app/core/exceptions.py`、`shared/api/ApiResponse.java` |
| `code` | 业务结果码。Java 为数字（成功固定 `0`），Agent 为字符串（如 `session_not_found`） | 同上 |
| 信封（envelope） | 统一响应外壳：Java `{code, message, data, requestId}`；Agent 成功无信封，仅错误用 `{code, message, request_id}` | `shared/api/ApiResponse.java`、`agent-service/app/core/exceptions.py` |
| 服务令牌 | `token_use=service` 的 RS256 JWT，由 Java `ServiceTokenService` 签发，只带 scope、只可访问 `/internal/v1/**` | `InternalAuthController.java`、`agent-service/app/services/control_plane.py` |
| SSE | Server-Sent Events，Agent 对话流协议，事件为 `token` / `reasoning` / `tool_call` / `tool_result` / `citations` / `done` / `error` | `agent-service/app/api/v1/sse.py` |
| 模型运行时 | Java `model` 模块提供的模型目录、BYOK 凭证、额度与用量控制面；开关 `MODEL_RUNTIME_ENABLED` / `BYOK_ENABLED` | `application-service/**/model/**`、`docs/model-runtime-architecture.md` |

## 4. 阅读路径

日常改代码不要按本表走完整链路：先查 [INDEX.md](INDEX.md) 的最小必读表，只读命中项。下表用于系统学习或跨端大改动。

| 场景 | 建议顺序 |
| --- | --- |
| 第一次接触项目 | [architecture-overview.md](architecture-overview.md) → 所在端的服务 `architecture.md` |
| 改前端 | [services/frontend/architecture.md](services/frontend/architecture.md) → [development-guide.md](services/frontend/development-guide.md) → [ui-design-system.md](services/frontend/ui-design-system.md) → [development-rules.md](development-rules.md) §1 |
| 改 Java | [services/application-service/architecture.md](services/application-service/architecture.md) → [security.md](services/application-service/security.md) → [development-guide.md](services/application-service/development-guide.md) |
| 改 Agent | [services/agent-service/architecture.md](services/agent-service/architecture.md) → [agent-workflows.md](services/agent-service/agent-workflows.md) → [api-reference.md](services/agent-service/api-reference.md) |
| 改管理端 | [services/admin/architecture.md](services/admin/architecture.md) → [services/admin/development-guide.md](services/admin/development-guide.md) → [development-rules.md](development-rules.md) §1 |
| 改接口 / 契约 | [api-contract.md](api-contract.md) 对应小节 → [development-rules.md](development-rules.md) §1 影响矩阵 → 两端服务文档 |
| 要上线 / 配环境 | [deployment/deployment-guide.md](deployment/deployment-guide.md) → [deployment/environment-variables.md](deployment/environment-variables.md) |
| 看当前待办 | [planning/closure-plan.md](planning/closure-plan.md) |
| 看未验证项与发布条件 | [planning/closure-plan.md](planning/closure-plan.md) §1–§4 |
| 新增或整理文档 | [documentation-governance.md](documentation-governance.md) |

## 5. 单一事实来源（SSOT）

同一事实只在一处详细维护，其他文档只链接。完整表见 [documentation-governance.md](documentation-governance.md) §5。

| 主题 | 唯一权威 |
| --- | --- |
| 系统架构、服务边界、数据归属、通信链路 | `architecture-overview.md` |
| 对外 HTTP / SSE / 内部接口契约 | `api-contract.md` 摘要 + 服务 `api-reference.md` 字段细节 |
| 环境变量与生产 fail-fast | `deployment/environment-variables.md` |
| 部署 / CI / 回滚 | `deployment/deployment-guide.md` |
| 技术决策 | `adr/**` |
| 当前待办 | `planning/closure-plan.md` |
| 当前未完成 / 未验证事项 | `planning/closure-plan.md` |
| 编码硬约束 | `.trae/rules/**` |

## 6. 维护规则

1. 契约变更必须同时更新 `api-contract.md`、受影响服务文档与代码，不允许只改一处。
2. 不为求完整而创建文档；没有证据支撑的内容不写，或明确标记为待确认。
3. 新增公共 API、配置项、环境变量时同步 `.env.example` 与 [deployment/environment-variables.md](deployment/environment-variables.md)。
4. 文档只描述当前代码的真实行为；历史契约由 Git 历史保留，不在文档中堆积。
5. 归档优先于删除；删除前必须确认「完全重复、无历史价值、无审计证据、无外部引用、已由权威文档完整承接」。
