# 文档地图（唯一导航入口）

| 项 | 内容 |
| --- | --- |
| 状态 | Current |
| 最后更新 | 2026-11-17 |
| 权威性 | Authoritative（文档全量清单；按任务的最小阅读路径见 [INDEX.md](INDEX.md)） |

仓库内只有根 `docs/` 是各端公共契约的权威来源。`frontend/docs/`、`application-service/docs/` 已被 `.gitignore` 排除；`agent-service/docs/` 不存在。三者都不构成权威文档。

**冲突优先级（唯一规则）**：代码 > `.env.example` 等可执行配置 > 本仓库权威文档 > 历史归档。

## 1. 文档清单

### 1.1 项目级与公共契约

| 文档 | 类型 | 内容 |
| --- | --- | --- |
| [INDEX.md](INDEX.md) | 导航 | 按任务的最小必读清单、规则路由、派生文档说明 |
| [README.md](README.md) | 导航 | 本文档，全量清单、术语与 SSOT |
| [architecture-overview.md](architecture-overview.md) | 事实 | 各端职责、部署拓扑、调用关系、信任边界、未实现能力 |
| [api-contract.md](api-contract.md) | 契约（**唯一事实源**） | Java / Agent / 内部接口、SSE、错误码、PC 配置 §5.7 |
| [api-contract-quick-reference.md](api-contract-quick-reference.md) | 派生速查 | API 契约速查视图 |
| [development-rules.md](development-rules.md) | 规范 | 跨端变更影响矩阵、验证命令、评审清单 |
| [documentation-governance.md](documentation-governance.md) | 规范 | 文档分类、目录、状态、SSOT、变更与门禁 |
| [model-runtime-architecture.md](model-runtime-architecture.md) | 设计 | 模型接入与调度、控制面/数据面、BYOK |

### 1.2 部署与运维

| 文档 | 类型 | 内容 |
| --- | --- | --- |
| [deployment/deployment-guide.md](deployment/deployment-guide.md) | 手册 | 环境要求、本地与全栈启动、Nginx、CI、发布与回滚、排障 |
| [deployment/solo-mode.md](deployment/solo-mode.md) | 手册 | Solo 模式命令、dev-token、curl 流式对话、能力边界 |
| [deployment/environment-variables.md](deployment/environment-variables.md) | 手册（**环境变量权威**） | 变量分组、默认值、生产 fail-fast、密钥生成与轮换 |
| [deployment/env-quick-reference.md](deployment/env-quick-reference.md) | 派生速查 | 环境变量速查视图（源：environment-variables） |

### 1.3 服务文档

| 文档 | 类型 | 内容 |
| --- | --- | --- |
| [services/frontend/architecture.md](services/frontend/architecture.md) | 事实 | React 分层、路由、状态、HTTP 门面、SSE 消费 |
| [services/frontend/development-guide.md](services/frontend/development-guide.md) | 规范 | 命令、目录、新增页面/接口/事件、样式与门禁 |
| [services/frontend/ui-design-system.md](services/frontend/ui-design-system.md) | 规范 | 设计 Token、控件尺寸、组件状态、验收基线 |
| [services/frontend/ui-quick-reference.md](services/frontend/ui-quick-reference.md) | 派生速查 | UI Token 与控件速查 |
| [services/frontend/generative-ui.md](services/frontend/generative-ui.md) | 事实 | OpenUI 渲染链路、组件库、持久化、安全与降级 |
| [services/application-service/architecture.md](services/application-service/architecture.md) | 事实 | Java 模块、分层、Flyway、数据访问、PC 配置模块 |
| [services/application-service/api-reference.md](services/application-service/api-reference.md) | 契约 | Java 端点字段、错误码、内部接口实现要点 |
| [services/application-service/security.md](services/application-service/security.md) | 事实 | RS256、刷新会话、过滤链、来源校验、生产守卫 |
| [services/application-service/development-guide.md](services/application-service/development-guide.md) | 规范 | 目录、命名、事务、Flyway、门禁 |
| [services/agent-service/architecture.md](services/agent-service/architecture.md) | 事实 | Agent 分层、生命周期、数据归属、已知问题 |
| [services/agent-service/agent-workflows.md](services/agent-service/agent-workflows.md) | 事实 | 9 节点图、状态、工具、HITL、checkpointer、时序 |
| [services/agent-service/api-reference.md](services/agent-service/api-reference.md) | 契约 | Agent 端点、SSE 事件、错误码 |
| [services/admin/architecture.md](services/admin/architecture.md) | 事实 | 管理端定位、目录、认证、路由守卫、页面能力、边界 |
| [services/admin/development-guide.md](services/admin/development-guide.md) | 规范 | 命令、环境变量、新增页面/接口、认证检查、部署 |

### 1.4 PC 配置主题

| 文档 | 内容 |
| --- | --- |
| [pc-config/README.md](pc-config/README.md) | 模块入口、当前基线与 SSOT |
| [pc-config/architecture.md](pc-config/architecture.md) | 三端职责、调用链、选型权与事实权威 |
| [pc-config/compatibility-rules.md](pc-config/compatibility-rules.md) | 9 条兼容规则的唯一详细说明 |
| [pc-config/data.md](pc-config/data.md) | 运行时夹具、快照、数据质量、治理产物 |
| [pc-config/market-offer-management.md](pc-config/market-offer-management.md) | 平台观测价、核验升级与发布 |
| [pc-config/testing-and-evaluation.md](pc-config/testing-and-evaluation.md) | 测试矩阵、评测命令与断言 |
| [pc-config/glossary.md](pc-config/glossary.md) | 领域术语与中文命名 |

Agent 图、状态、工具与 HITL 的详细说明统一在 [services/agent-service/agent-workflows.md](services/agent-service/agent-workflows.md)，`pc-config/` 不再维护第二份。

### 1.5 决策、规划与质量

| 文档 | 类型 | 内容 |
| --- | --- | --- |
| [adr/README.md](adr/README.md) | 索引 | 现行 ADR 清单、状态与阅读顺序 |
| `adr/` 现行 8 份 | 决策 | 架构决策记录，不可变；从索引进入 |
| [planning/roadmap.md](planning/roadmap.md) | 规划（**阶段状态与遗留问题权威**） | 当前基线、阶段状态、遗留问题、下一阶段边界 |
| [planning/pc-config-agent-refactor-plan-v1.md](planning/pc-config-agent-refactor-plan-v1.md) | 规划 | LLM 主导选型的重构目标、落地结果与未完成项 |
| [quality/hardware-data-governance-report.md](quality/hardware-data-governance-report.md) | 质量证据 | 离线治理输入、状态分布、跑分映射、候选池与限制 |
| [quality/hardware-data-baseline.md](quality/hardware-data-baseline.md) | 质量证据 | 硬件数据基线 |

## 2. 信息状态标签

| 标签 | 含义 |
| --- | --- |
| **已验证事实** | 有源码、配置、迁移脚本、测试或实际运行结果支撑，文中给出证据位置 |
| **已确认决策** | 项目负责人明确同意、但可能尚未全部落地 |
| **待确认事项** | 尚未决定，或需跨端协商 |
| **待验证假设** | 有依据但证据不足 |
| **未实现能力** | 设计与文档中提到，但当前代码没有实现 |
| **规划中** | 有明确方向但尚未排期或开工，不得写成现有能力 |
| **历史信息** | 仅解释背景，不得作为当前契约 |

写作时使用「（已验证，`路径`）」「【已确认决策】」「【规划中】」「【未实现】」这类显式标记。

## 3. 术语

跨端通用术语如下；PC 领域术语见 [pc-config/glossary.md](pc-config/glossary.md)。

| 术语 | 含义 | 出处 |
| --- | --- | --- |
| `thread_id`（客户端） | 前端维护的会话标识，长度 1..64；业务表以 `(user_id, thread_id)` 隔离 | `agent-service/app/api/v1/chat.py`、`app/services/session_store/interface.py` |
| 检查点线程键 | 服务端由 `namespaced_thread_id(user, client_thread_id)` 派生，只用于 checkpointer 与分布式锁 | `app/core/security.py` |
| `user_id` | JWT 的 `sub`；Java 签发的是 `users.public_id`（UUID） | `JwtTokenService.java`、`app/api/v1/auth.py` |
| Access Token | RS256 JWT，只存前端内存，有效期 `JWT_ACCESS_TTL`（默认 `10m`） | `JwtTokenService.java` |
| Refresh Token | 32 字节不透明随机串，仅经 `HttpOnly` Cookie `agent_refresh` 传输 | `RefreshSessionService.java` |
| `request_id` / `requestId` | 单请求追踪标识，来自 `X-Request-Id` | `agent-service/app/core/exceptions.py` |
| 服务令牌 | `token_use=service` 的 RS256 JWT，只能访问 `/internal/v1/**` | `ServiceTokenService.java` |
| SSE | Agent 对话流协议：`token` / `reasoning` / `tool_call` / `tool_result` / `citations` / `interrupt` / `done` / `error` | `app/api/v1/sse.py` |
| 事实权威 | 对规格、价格、兼容与预算的最终判定权，归 Java | [pc-config/architecture.md](pc-config/architecture.md) §2 |
| 选型决策权 | 决定选哪一个 `hardware_id` 的权力，归 Agent LLM | 同上 |

## 4. 阅读路径

日常改代码先查 [INDEX.md](INDEX.md)。下表用于系统学习或跨端大改动。

| 场景 | 建议顺序 |
| --- | --- |
| 第一次接触项目 | [architecture-overview.md](architecture-overview.md) → 所在端 `architecture.md` |
| 改前端 | [frontend/architecture.md](services/frontend/architecture.md) → [development-guide.md](services/frontend/development-guide.md) → [ui-design-system.md](services/frontend/ui-design-system.md) |
| 改 Java | [application-service/architecture.md](services/application-service/architecture.md) → [security.md](services/application-service/security.md) → [development-guide.md](services/application-service/development-guide.md) |
| 改 Agent | [agent-service/architecture.md](services/agent-service/architecture.md) → [agent-workflows.md](services/agent-service/agent-workflows.md) → [api-reference.md](services/agent-service/api-reference.md) |
| 改 PC 配置 | [pc-config/README.md](pc-config/README.md) → [agent-workflows.md](services/agent-service/agent-workflows.md) → [compatibility-rules.md](pc-config/compatibility-rules.md) |
| 改接口 / 契约 | [api-contract.md](api-contract.md) 对应小节 → [development-rules.md](development-rules.md) §1 |
| 要上线 / 配环境 | [deployment/deployment-guide.md](deployment/deployment-guide.md) → [deployment/environment-variables.md](deployment/environment-variables.md) |
| 看当前待办 | [roadmap.md](planning/roadmap.md) §5 |
| 新增或整理文档 | [documentation-governance.md](documentation-governance.md) |

## 5. SSOT

| 主题 | 唯一权威 |
| --- | --- |
| 系统架构、服务边界、数据归属、通信链路 | [architecture-overview.md](architecture-overview.md) |
| 对外 HTTP / SSE / 内部接口契约 | [api-contract.md](api-contract.md) |
| PC 兼容规则 | [pc-config/compatibility-rules.md](pc-config/compatibility-rules.md) |
| Agent 图与节点行为 | [services/agent-service/agent-workflows.md](services/agent-service/agent-workflows.md) |
| 环境变量与生产 fail-fast | [deployment/environment-variables.md](deployment/environment-variables.md) |
| 部署 / CI / 回滚 | [deployment/deployment-guide.md](deployment/deployment-guide.md) |
| 技术决策 | `adr/**` |
| 阶段状态与遗留问题 | [planning/roadmap.md](planning/roadmap.md) |
| 编码硬约束 | `.trae/rules/**` |

## 6. 维护规则

1. 契约变更必须同时更新 `api-contract.md`、受影响服务文档与代码。
2. 不为求完整而创建文档；没有证据支撑的内容不写，或明确标记为待确认。
3. 新增公共 API、配置项、环境变量时同步 `.env.example` 与 [deployment/environment-variables.md](deployment/environment-variables.md)。
4. 文档只描述当前代码的真实行为；历史契约由 Git 保留。
5. 删除文档前必须确认「完全重复或无独立价值、无外部引用、已由权威文档完整承接」；ADR 不可修改。
