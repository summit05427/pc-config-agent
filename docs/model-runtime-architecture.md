# 模型接入与调度架构设计

| 项 | 内容 |
| --- | --- |
| 状态 | Current |
| 最后核验 | 2026-11-07 |
| 权威性 | Authoritative（模型运行时设计决策与落地进度；模型出口归属以 ADR 0008 为准） |
| 主要证据 | `application-service/**/model/**`、`db/migration/V7–V23`、`agent-service/app/services/{control_plane,model_usage,llm}.py`、`deploy/litellm/config.yaml`、`frontend/src/features/{models,usage}/api/**` |

状态说明：**设计稿 + 已落地**。PR1–PR6 均已实现（PR6 见 PR #3，各章节标题标注了落地进度）。依据原始方案、Round 1 决策与 Round 2 四项决策修订而成（原方案文档已于 2026-11-05 清理，历史见 Git）。
标注约定见 [README.md](README.md) §2：已验证事实 / 已确认决策 / 待确认事项 / 未实现能力 / 历史信息。

> 2026-11-01 修订：补齐元信息；§1 明确标注为迁移前快照；修正 v2 分页端点的落地状态；历史段落中引用的 Vue 路径与已删除的 `configuration.md` 仅作历史记录，当前对应关系见 [services/frontend/architecture.md](services/frontend/architecture.md) 与 [deployment/environment-variables.md](deployment/environment-variables.md)。

> 2026-11-07 修订：模型出口已统一到 LiteLLM 网关（[ADR 0008](adr/0008-unified-model-egress-litellm.md)），Agent 侧模型 Adapter 已删除。§2 D4「不引入 LiteLLM」、§10.2 的 Adapter 与缓存描述仅保留为历史决策记录，不再代表当前实现；reasoning 能力位见 `V23__add_model_reasoning_capabilities.sql`。

本文只把「已在代码中成立的事实」写成事实；其余一律标注为「未实现」或「待确认」。禁止把本文章节当作已存在的接口或表。

## 1. 现状基线（已验证事实）

> 本节是 **Vue 前端迁移前（2026-10-31）的快照**，用于解释下面各节的设计起点。其中 `frontend/src/stores/agent-chat.ts`、`views/settings/sections/AgentSection.vue` 等 Vue 路径已随迁移移除，当前 React 对应关系见 [services/frontend/architecture.md](services/frontend/architecture.md)；后端与 Agent 的引用仍可直接核对。

| 事实 | 证据 |
| --- | --- |
| Agent 只有一个全局模型实例：`get_chat_model()` 用无参 `lru_cache`，进程内唯一 | `agent-service/app/services/llm.py:49-73` |
| 只有 `openai` 可用；`LLMSettings.provider` 允许 `azure_openai`，但运行期被 `_validate_llm_settings` 拒绝 | `agent-service/app/services/llm.py:21-28`、`app/core/config.py:37` |
| 模型参数来自单组 `LLM__*` 环境变量；无请求级、无用户级模型参数 | `docker-compose.yml:191-196`、`agent-service/.env.example` |
| 图中只有 1 个 LLM 节点 `model`，与 `tools` 之间条件边循环；无模型角色概念 | `agent-service/app/agent/graph.py:88-129` |
| `ChatRequest` 只有 `message`/`thread_id`/`preferences`，无 `model` 字段 | `agent-service/app/api/v1/chat.py:60-74` |
| 前端对话请求体同样只有 `message`/`thread_id`/`preferences`；设置页无模型、Provider、Key 管理 | `frontend/src/stores/agent-chat.ts:437-450`、`views/settings/sections/AgentSection.vue:71-155` |
| Agent 无出站 HTTP 客户端依赖（`httpx` 仅在 dev 依赖组）；`application-service` 无任何 HTTP 客户端 | `agent-service/pyproject.toml:27-36`；`architecture-overview.md` §3 |
| Java 迁移仅 V1–V6（users / refresh_sessions / users 扩展 / user_preferences / auth_audit_logs / baseline），无模型相关表 | `application-service/src/main/resources/db/migration/` |
| `session_meta` 现有列：`user_id`、`thread_id`、`title`、`created_at`、`updated_at`、`last_active_at`；主键 `(user_id, thread_id)` | `agent-service/app/services/session_store/postgres.py:18-40` |
| Agent 验签要求 `token_use="access"`，未知 `kid` 直接拒绝，只认本进程公钥白名单 | `agent-service/app/core/security.py:108-144` |
| Java 资源服务器只校验签名/issuer/audience，**未见 `token_use` 校验**（全仓检索 `token_use` 仅命中签发处） | `shared/config/SecurityConfig.java:73-101`、`identity/infrastructure/JwtTokenService.java:37` |

由此可得两条结论：

1. **Managed 模式已天然存在**：平台密钥即当前 `LLM__API_KEY`。Phase 1 是「加控制面 + 加选择能力 + 加计量」，不是从零重建。
2. **模型切换当前不可能生效**：必须先把 `lru_cache` 无参单例改为按 `(provider, model_id, credential_id)` 键缓存，否则任何上层选择都是假的。

## 2. 已确认决策（Round 1 + Round 2）

| 编号 | 决策 |
| --- | --- |
| D1 | 接受 Agent → Java 的内部只读调用；凭证按「已授权任务」发放，不接受按任意 `user_id` 查凭证 |
| D2 | Phase 1 拆两段：PR1–3（Managed + 会话级选择 + 调用明细）、PR4–6（BYOK 连接、凭证验证、BYOK 调用与额度） |
| D3 | Java 是 Provider Registry / Model Registry / 用户可用性的权威；Agent 只做运行期解析、角色解析、Adapter 与错误分类 |
| D4 | 【已被 ADR 0008 取代】薄 Adapter，不引入 LiteLLM；缓存键用 `(provider, model, credential_id)`，禁止用原始 Key 作键；首批走 OpenAI 兼容协议 |
| D5 | 环境变量主密钥 + AES-256-GCM + `key_version`；不引入外部 KMS，但保留密钥管理抽象；Java 解密，Agent 不持主密钥 |
| D6 | Auto = 平台默认模型（不做评分/竞价/跨 Provider 自动切换）；支持单请求覆盖与会话级选择，请求级不改变会话默认 |
| D7 | **使用明细唯一事实源在 Java**：Agent 采集并上报，Java 校验、按 `invocation_id` 幂等去重、持久化、查询；Agent 不建第二套业务台账 |
| D8 | **会话模型存 `session_meta.model_key`**：值为稳定标识 `<provider_code>:<model_key>`，不等于展示名、不含凭证；`NULL` 即 Auto；已有会话迁移后保持 `NULL` |
| D9 | **新增 `PUT /sessions/{thread_id}/model`**：只改会话级选择，幂等，校验会话归属 / 目录存在 / 用户可用性，并返回最新模型配置 |
| D10 | **额度 = 每日请求数（UTC 自然日）**：按 `user_id` 统计，任务授权通过后原子扣减；超限 HTTP 429 + `quota_exceeded`；Managed 与 BYOK 共用该额度 |
| D11 | **失败上报不等于调用失败**：使用明细上报独立异步重试，不得改变 SSE 结果；Token 用量拿不到就留空，不伪造 |
| D12 | **C1 裁决**：不改 Java 数字码体系；Java 统一信封新增**顶层可选** `errorType`（仅错误响应输出，成功响应不输出）；Agent 对外继续只用字符串 `code`，需要一个薄映射层把 Java 数字码 → Agent 字符串码。禁止把 `errorType` 放进 `data`（错误时 `data` 通常为 `null`，混入字段会让前端无法区分「渲染数据」与「报错」） |

## 3. 架构总览（PR1–PR6 已实现）

```text
                    ┌─────────────────────────────┐
浏览器 ──JWT──> Nginx ──/api/──> │  application-service (8080) │  控制面
                    │  ├ Model Registry (providers/models) │
                    │  ├ Provider Connection / Credential  │
                    │  ├ Runtime Task 授权 + 额度原子扣减    │
                    │  └ Model Usage 台账                   │
                    └───────────▲─────────────────┘
                                │ 内部只读 API（服务令牌 + 用户令牌）
                                │ /internal/v1/**（不经 Nginx 暴露）
                    ┌───────────┴─────────────────┐
浏览器 ──JWT──> Nginx ──/agent/──>│  agent-service (8000)        │  数据面
                    │  ├ Runtime Resolver（按角色解析）      │
                    │  ├ Model Adapter（openai-compatible）  │
                    │  ├ LangGraph 执行 + SSE                │
                    │  └ 调用明细上报（异步、幂等）           │
                    └─────────────────────────────┘
```

- 不新增第四服务；控制面能力放进 `application-service` 的 `identity` 模块之外的新模块（命名待定，见 §11-Q9）。
- 依赖方向新增一条 **Agent → Java** 的内部调用；**Java 仍不调用 Agent**，既有决策不变。
- `LLM__API_KEY` 保留为「Managed 平台密钥」，不进入任何响应、日志、SSE、checkpointer。

## 4. 凭证通道时序（§4.1 Managed 已实现；§4.2 BYOK 调用链已在 PR5 实现）

### 4.1 Managed（PR1–3）

```text
浏览器            Agent                        Java
  │ POST /chat/stream │                           │
  │──────────────────>│                           │
  │                   │ POST /internal/v1/model-tasks
  │                   │ (ServiceToken + UserToken, thread_id, requested_model?)
  │                   │──────────────────────────>│ 1 校验服务令牌范围 + 用户令牌
  │                   │                           │ 2 校验模型目录/用户可用性
  │                   │                           │ 3 原子扣减当日请求额度
  │                   │                           │   （超限 → 429 quota_exceeded）
  │                   │                           │ 4 写 model_runtime_tasks（TTL 10m）
  │                   │<──────────────────────────│ {task_id, provider, model_key,
  │                   │                           │  credential_source=MANAGED}
  │                   │ 使用平台密钥（进程环境变量）│
  │                   │ 执行图 → SSE token/tool…   │
  │                   │ 每次模型调用：生成 invocation_id
  │                   │ POST /internal/v1/model-usage（批量、幂等、异步重试）
  │                   │──────────────────────────>│ 按 invocation_id 去重后入库
  │<──SSE done────────│                           │
```

### 4.2 BYOK 调用链（PR5 已实现；PR4 负责连接与凭证的录入、加密存储与撤销）

```text
Agent                                   Java
  │ 1. POST /internal/v1/model-tasks        │
  │    (ServiceToken + UserToken)           │ 校验凭证归属、状态、模型可用性
  │────────────────────────────────────────>│ 返回 task_id + credential_id + source=BYOK
  │ 2. POST /internal/v1/model-tasks/{id}/credential-lease
  │    (仅 ServiceToken，任务未过期且未撤销)
  │────────────────────────────────────────>│ 解密（AES-GCM，主密钥在 Java）
  │<────────────────────────────────────────│ {credential_type, secret, expires_in}
  │ 3. 内存持有至任务结束，用完即弃          │
  │ 4. 调用 Provider（openai-compatible）   │
  │ 5. POST /internal/v1/model-usage        │ 按 invocation_id 幂等入库，
  │    (每调用一个 invocation_id)            │ credential_source=BYOK
  │────────────────────────────────────────>│
```

约束：

- 第 2 步是**独立的一次性兑换**，绝不与第 1 步合并返回；配置响应里永远不含明文密钥。
- 严格一次性：Java 用 `leased_at IS NULL` 条件更新占位，重复兑换返回 409 `40215`；进程重启或任务结束时 Agent 不得复用旧明文。
- 兑换只接受服务令牌（`token_use=service` + scope `model-runtime:read`），不校验用户令牌；用户身份在任务创建时已成对校验并绑定到任务行。
- 任务过期、凭证撤销/删除、用户被禁用后，第 2 步必须失败，不得使用进程内残留对象：任务过期 404 `40206`、已撤销 401 `40216`、非 BYOK 409 `40218`、显式模型未通过可用性校验 422 `40219`。
- 明文密钥只存在于 Agent 单次任务的内存作用域；禁止写入 `AgentState`、checkpointer、`session_messages`、日志、异常、SSE、Tracing。
- `credential_id` 不参与日志明文输出，用哈希前缀代替。
- BYOK 与 Managed 共用每日请求额度：额度在任务创建阶段已原子扣减，BYOK 只免 Provider 费用，不免平台请求额度。

## 5. 服务间认证（PR1 已实现）

| 项 | 设计 | 说明 |
| --- | --- | --- |
| 身份 | Agent 以 `client_credentials` 换取服务令牌 | `POST /internal/v1/auth/service-token`，表单 `client_id` + `client_secret` |
| 令牌 | RS256 JWT，复用现有签发密钥 | claims：`token_use="service"`、`scope=["model-runtime:read","model-usage:write"]`、`aud`=现有 audience、TTL 默认 5 分钟（`INTERNAL_AUTH_TOKEN_TTL`） |
| 校验 | Java 端 `/internal/v1/**` 只接受 `token_use="service"` 且 scope 匹配；`/api/v1/**` 只接受 `token_use="access"` | **必须新增过滤**：当前 Java 未校验 `token_use`（§1 已验证），否则服务令牌可被当作访问令牌使用 |
| 用户绑定 | `/internal/v1/model-tasks` 额外携带用户 Access Token | 服务身份与用户身份分开校验，避免「传 user_id 即可取凭证」 |
| 过期与轮换 | 服务令牌短 TTL；`client_secret` 走环境变量，支持双密钥并存窗口后轮换；签名密钥沿用 `kid` 轮换机制 | 双密钥窗口为计划项，PR1 只做单密钥 + 重启轮换 |
| 暴露面 | `/internal/v1/**` 不经 Nginx 代理；仅容器网络可达 | Nginx 仅有 `/api/` 与 `/agent/` 两个 location（已验证），但需在 PR1 增加显式回归验证 |

## 6. 凭证安全边界与生命周期（PR4 已落地录入/存储/回显/撤销；PR5 已落地 lease 与多版本密钥环解密；重加密轮换仍为后续）

| 阶段 | 要求 |
| --- | --- |
| 录入 | 前端经 HTTPS 提交到 Java；不在前端持久化（禁止写入 localStorage / sessionStorage / 任何前端状态库） |
| 存储 | AES-256-GCM；每次加密唯一 nonce（12 字节）与认证标签，连同 `key_version` 一起入库；密文结构 `v1:<key_version>:<base64(nonce|tag|ciphertext)>` |
| 主密钥 | `MODEL_CRED_MASTER_KEYS`（形如 `<version>:<base64>`，逗号分隔，可持多个版本）只注入 Java；当前加密版本由 `MODEL_CRED_KEY_VERSION` 指定；单版本回退项 `MODEL_CRED_MASTER_KEY` 仅用于兼容旧配置；与业务库分离，不提交、不进镜像、不进前端 |
| 回显 | 创建/查询只返回 `credential_id`、掩码（如 `sk-****abcd`）、`status`、`last_verified_at`；不提供回读接口 |
| 传输 | 只在 `/internal/v1/.../credential-lease` 响应中出现，同容器网络，禁止写入访问日志（需关闭该 location 的请求体日志） |
| 使用 | 任务内内存持有，任务结束即释放；缓存失效由 `credential_id` + 凭证版本号驱动 |
| 撤销 | 删除/撤销后：DB 置 `REVOKED` → 任务授权拒绝 → lease 拒绝 → Agent 缓存失效（`invalidate_credential`）；三步都有测试 |
| 轮换 | 新增 `key_version` 后新密文用新版本；密钥环保留旧版本以支持**多版本兼容解密**（PR5 已实现，按密文中的 `key_version` 选主密钥）；后台逐步重加密为后续 |
| 备份 | 主密钥与数据库备份分开保管；丢失主密钥等于凭证全丢，需在部署文档写明 |
| 禁止 | 自行实现密码学算法；密钥出现在日志、异常、SSE、Tracing、数据库明文列 |

## 7. 职责边界（PR1–PR5 已落地）

| 组件 | 负责 | 不负责 |
| --- | --- | --- |
| Java Model Registry | Provider 目录、Model 目录、能力元数据、来源与更新时间、用户可用性判定 | 不做模型调用、不解析 LangGraph 角色 |
| Java Credential Vault | 加解密、掩码、状态、轮换、lease 授权 | 不向浏览器返回明文 |
| Java Runtime Task | 授权记录、TTL、归属校验、额度原子扣减 | 不执行对话 |
| Java Usage Ledger | 按调用累加 token/耗时/状态/费用归属 | 不保存完整对话 |
| Agent Runtime Resolver | 角色 → 模型解析、用户覆盖校验、任务创建、失败分类 | 不维护第二套权威目录、不自行探测 Provider 目录 |
| Agent Adapter | 按 `ProviderSpec` 构造模型客户端、缓存与失效 | 不读取数据库中的凭证、不做用户鉴权 |
| LangGraph 节点 | 声明所需角色与能力 | 不硬编码 provider/model/key |

能力三层必须分开记录，不得合并：

1. 模型理论能力（Registry 静态目录，含来源与 `verified_at`）。
2. Provider 实际提供能力（验证结果，可能滞后）。
3. 当前凭证实际可访问（用户级验证状态，`AVAILABLE` / `UNAVAILABLE` / `UNVERIFIED`）。

## 8. 数据模型（V7–V10、V11–V12 已建表，PR1/PR4；V13–V14 已建表，PR5）

Java（`agent` 库，Flyway V7+）：

| 表 | 关键列 | 说明 |
| --- | --- | --- |
| `providers` | `code`(PK)、`display_name`、`protocol`、`default_base_url`、`enabled`、`created_at` | 静态种子（OpenAI / DeepSeek / Qwen / Volcengine / Gemini 走 `openai-compatible`，Anthropic 走 `anthropic-messages`，V22）；设置页供应商选择器以本表为权威；V14 已清空写死的第三方域名，新连接地址来自配置 `app.model.provider-default-base-urls` 或用户输入 |
| `models` | `id`、`provider_code`、`model_key`、`display_name`、`context_window`、`capabilities`(jsonb)、`capability_source`、`verified_at`、`enabled`、`byok_only`(V22) | 目录唯一权威；`byok_only=true` 的条目只在用户接入对应 Provider 后可见；`byok_only=false` 的平台条目还要求 `ManagedModelAvailability` 真实探测平台密钥可用 |
| `provider_connections` | `id`、`user_id`、`provider_code`、`base_url`、`status`、`last_verified_at` | Phase 1 每 Provider 每用户 1 条 |
| `provider_credentials` | `id`、`connection_id`、`user_id`、`credential_type`、`ciphertext`、`key_version`、`masked_hint`、`status`、`created_at`、`revoked_at` | 只存密文；`key_version` 对应密钥环中的版本，支持多版本兼容解密 |
| `model_runtime_tasks` | `id`、`user_id`、`thread_id`、`requested_model`、`resolved_model`、`credential_source`、`credential_id`、`status`、`expires_at`、`created_at`、`leased_at`(V13)、`base_url`(V13) | 凭证授权凭据；`leased_at` 非空即表示已一次性兑换，条件 UPDATE 兜底并发重复兑换；`base_url` 为 BYOK 任务创建时的地址快照 |
| `model_usage_records` | `id`、`invocation_id`(唯一)、`task_id`、`user_id`、`thread_id`、`model_role`、`provider`、`model_key`、`credential_source`、`prompt_tokens`(可空)、`completion_tokens`(可空)、`latency_ms`(可空)、`status`、`error_type`(可空)、`estimated_cost`(可空)、`cost_status`、`cost_bearer`、`currency`(可空)、`occurred_at`、`created_at` | 使用明细唯一事实源；唯一索引 `uk_usage_invocation(invocation_id)`，普通索引 `(user_id, occurred_at DESC)` |
| `model_pricing` | `id`、`provider`、`model_key`、`currency`、`input_price_per_million`、`output_price_per_million`、`effective_from`、`created_at` | 版本化定价（V16）；唯一约束 `(provider, model_key, effective_from)`；单价按「每百万 token」，`NUMERIC(18,6)`；由运营维护，Agent 不持有定价数据 |
| `model_request_quotas` | `user_id`、`quota_date`(DATE, UTC)、`used_count`、`limit_count`、`updated_at` | 主键 `(user_id, quota_date)`；`limit_count` 在当日首次请求时按配置快照写入，中途改配置次日生效 |

> **成本统计口径（B-07，2026-10-31；示例定价 V20，2026-11-04）**：未录入定价的模型成本一律记为 `UNKNOWN`，**不猜测金额、不写 0**。定价按 `(provider, model_key, effective_from)` 版本化，由运营通过管理端维护（D-05，2026-11-01 已实现，接口见 `docs/api-contract.md` §5.1；SQL 迁移仍可用于初始化）；成本解析按调用发生时间选择不晚于该时刻的最新版本，历史用量不会被后续调价改写。BYOK 调用记为 `BYOK_NOT_BILLED`，平台不承担费用。`ModelUsageReconciliationJob` 同时检查 `ESTIMATED` 必须有金额与币种、其他状态必须没有金额。
>
> **示例定价（模板口径）**：`V20__seed_model_pricing_sample.sql` 为 `deepseek-flash` / `deepseek-v4-pro` 供入 DeepSeek 官方公开价（USD/百万 token，来源与抓取日期写在迁移注释），因表结构不支持峰谷与缓存命中区分，统一取「峰时 + 缓存未命中」最高档作为**保守上界**估算。`estimated_cost` 仅为成本观测值，**本模板不接入支付、账单、结算与余额扣费**；目录中的 `openai:gpt-4o` / `openai:gpt-4o-mini` 已由 V21 停用（当前只提供 DeepSeek 密钥），平台不再产生它们的用量，如重新启用需同步补价。运营替换示例价时新增一条更晚 `effective_from` 的版本即可，示例版本保留以复现历史成本。

Agent（`agent_service` 库，`STORAGE__AUTO_SETUP` 幂等 DDL）：

| 变更 | 说明 |
| --- | --- |
| `session_meta` 新增 `model_key VARCHAR(64) NULL` | 会话级选择，值格式 `<provider_code>:<model_key>`；`NULL` = Auto。幂等 DDL：`ALTER TABLE session_meta ADD COLUMN IF NOT EXISTS model_key VARCHAR(64)`，不重建表、不改主键、不加外键（跨库无法引用） |
| `model_key` 取值约束 | 长度 3..64，字符集 `[a-z0-9:-._]`；仅由 Java 目录判定合法性，Agent 只做格式校验；不保存展示名、不保存凭证、不保存 Provider 原始 key |
| 已有会话迁移 | 存量行保持 `NULL`，即 Auto；不回填、不猜测用户意图 |
| 删除会话 | 随 `session_meta` 行一起删除，无独立清理逻辑 |
| 独立 `model_invocation_records` | **不做**（D7 已定 Java 为唯一事实源）；Agent 仅保留进程内待上报队列与结构化日志 |

额度扣减 SQL（已实现，PR1；单语句原子）：

```sql
INSERT INTO model_request_quotas (user_public_id, quota_date, used_count, limit_count)
VALUES (:userPublicId, :utcDate, 1, :dailyLimit)
ON CONFLICT (user_public_id, quota_date) DO UPDATE
SET used_count = model_request_quotas.used_count + 1,
    updated_at = now()
WHERE model_request_quotas.used_count < model_request_quotas.limit_count
RETURNING used_count, limit_count;
```

返回 0 行即视为超限（既有行已用满），不得先查后改。

不做的事：不在 Agent 建用户表；不让 Agent 直接读写 Java 的凭证表；不跨库 JOIN。

## 9. API 草案（PR1–PR6 端点已实现）

Java 公开（现有信封 `{code,message,data,requestId}`，PR1 新增顶层可选 `errorType`，仅错误响应输出）：

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/v1/models` | 需登录 | 可选用模型列表：平台模型 + 用户已启用 BYOK 模型，含能力与可用性（全量数组，兼容保留） |
| GET | `/api/v2/models` | 需登录 | 模型目录分页版本（`{list,total,page,size}`，`page`/`size` 校验规则同全局分页） |
| GET | `/api/v1/model-connections` | 需登录 | 用户连接列表（PR4 已实现，只返回掩码，无明文与密文；全量数组，兼容保留） |
| GET | `/api/v2/model-connections` | 需登录 | 用户连接分页版本（字段与 v1 列表一致，按创建时间倒序） |
| POST | `/api/v1/model-connections` | 需登录 | 创建连接 + 凭证（PR4 已实现，加密后入库）；写入后自动验证一次，成功置 `VERIFIED`，失败保留 `UNVERIFIED` 且不回滚连接 |
| PUT | `/api/v1/model-connections/{id}` | 需登录 | 轮换凭证：旧凭证 `REVOKED`、写入新凭证并重置验证状态，保存后自动验证一次 |
| POST | `/api/v1/model-connections/{id}/verify` | 需登录 | 真实远程验证（PR5 已实现）：解密后调 Provider，优先 `GET /models`，不支持（404/405/501）时退化为 `max_tokens=1` 的最小 chat；成功写 `last_verified_at` 并置 `VERIFIED`，失败返回 422 `40219` 或 502 `40217`；单用户每分钟限 5 次，超限 429 `40222` |
| DELETE | `/api/v1/model-connections/{id}` | 需登录 | 删除连接（PR4 已实现：连接软删 + 凭证 `REVOKED`）；创建/轮换/验证/删除均写审计事件 |
| GET | `/api/v1/users/me/model-usage` | 需登录 | 用量概览（PR6 已实现）：当日额度快照 + 本人使用明细分页，支持 `from`/`to` 自然日过滤，见 §9.5 |

Java 内部（`/internal/v1/**`，不经 Nginx）：

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| POST | `/internal/v1/auth/service-token` | client 凭据 | 换取服务令牌 |
| POST | `/internal/v1/model-tasks` | 服务令牌 + 用户令牌 | 创建/复用运行时任务，返回解析结果（不含密钥） |
| GET | `/internal/v1/model-tasks/{id}` | 服务令牌 | 重新读取（TTL 内） |
| POST | `/internal/v1/model-tasks/{id}/credential-lease` | 服务令牌 | 一次性兑换明文凭证（PR5 已实现，仅 BYOK；重复兑换 409 `40215`） |
| POST | `/internal/v1/model-usage` | 服务令牌 + scope `model-usage:write` | 幂等上报，批量 1..20 条，按 `invocation_id` 去重 |
| POST | `/internal/v1/model-access/check` | 服务令牌 + 用户令牌 | 校验 `model_key` 是否在目录中且当前用户可用（供 `PUT /sessions/{id}/model` 使用） |

Agent 变更：

| 项 | 变更 |
| --- | --- |
| `ChatRequest` | 新增可选 `model`（单次覆盖，长度 ≤64，不改变会话默认；`null` 或省略即会话选择） |
| `PUT /sessions/{thread_id}/model`（新增） | 只改会话级选择；幂等；先校验会话归属，再经 `/internal/v1/model-access/check` 校验目录与可用性；失败不写库 |
| `GET /sessions` 与会话对象 | 增加只读字段 `model_key`（`null` 表示 Auto），供前端回显 |
| 新增出站客户端 | `app/services/control_plane.py`（httpx，超时 5s，失败策略见 §10.3） |

### 9.1 会话模型设置（PR3 已实现）

```http
PUT /agent/api/v1/sessions/{thread_id}/model
Authorization: Bearer <access_token>
Content-Type: application/json

{ "model_key": "openai:gpt-4o-mini" }   // 传 null 表示恢复 Auto
```

```json
{
  "thread_id": "t-demo",
  "model_key": "openai:gpt-4o-mini",
  "effective": "explicit",
  "model": {
    "provider": "openai",
    "display_name": "GPT-4o mini",
    "capabilities": ["text", "tool_calling"],
    "context_window": 128000
  },
  "updated_at": "2026-10-30T08:00:00Z"
}
```

- 幂等：重复提交相同 `model_key` 不修改 `updated_at`、不产生额外副作用，直接返回当前配置。
- 错误：会话不存在或非本人 404 `session_not_found`；格式非法 422 `validation_error`；目录不存在或用户无权使用 403 `model_not_available`；控制面不可达 503 `control_plane_unavailable`。
- 单次请求覆盖不走此接口，只由 `POST /chat/stream` 的 `model` 字段表达。

### 9.2 额度超限响应（PR1/PR2 已实现）

Agent 面向浏览器（裸 JSON 错误信封）：

```json
{
  "code": "quota_exceeded",
  "message": "今日请求额度已用尽，请明日再试",
  "request_id": "...",
  "quota": { "quota_type": "daily_requests", "limit": 100, "used": 100, "reset_at": "2026-10-31T00:00:00Z" }
}
```

- HTTP 429；在流建立前返回，因此不会出现「流内改状态码」问题。
- 配额由 Java 在 `model-tasks` 中扣减，Agent 只透传；Agent 不自行计数，避免两套计数漂移。
- Java 侧数字错误码与字符串码的映射见 §9.4（D12 已裁决）。
- Agent 不自行判断额度，只把 Java 的 429 与 `quota` 负载透传为字符串码 `quota_exceeded`。

### 9.3 使用明细上报（PR1/PR2 已实现）

```json
{
  "records": [
    {
      "invocation_id": "c1f0b1e0-...",
      "task_id": "9d2a...",
      "model_role": "conversation",
      "provider": "openai",
      "model_key": "openai:gpt-4o-mini",
      "credential_source": "MANAGED",
      "prompt_tokens": 120,
      "completion_tokens": 30,
      "latency_ms": 850,
      "status": "success",
      "error_type": null,
      "occurred_at": "2026-10-30T08:00:00Z"
    }
  ]
}
```

响应 `{ "accepted": 1, "duplicated": 0, "rejected": 0 }`。

> 命名说明：上面示例用 snake_case 描述的是 Agent 对外协议；Java 内部接口 DTO 一律 camelCase（如 `invocationId`、`credentialSource`），由 Agent 侧薄 Adapter 做字段映射，禁止把两套命名混进同一层。

- `invocation_id` 由 Agent 在每次真实模型调用时生成（UUIDv4），一次调用一个，不是一次对话一个。
- `prompt_tokens` / `completion_tokens` / `latency_ms` 允许为空，禁止填 0 或估算值冒充精确值。
- **成本不再由 Agent 上报（2026-10-31，B-07）**：Agent 不持有定价数据，上报中已移除 `estimatedCost`；Java 在入库时按 `model_pricing` 选择「不晚于 `occurred_at` 的最近一条」定价并在写入行上定格金额，后续调价不改写历史成本。
- 重复 `invocation_id` 计入 `duplicated`，不重复写库、不重复计费。
- `task_id` 必须存在于 `model_runtime_tasks` 且属于上报用户，否则计入 `rejected` 并记 warning（不返回 4xx 阻塞批量）。
- **持久化（2026-10-31）**：调用结束后先写 Agent 库 `usage_outbox`（单次 INSERT），再由后台循环批量投递；写库失败才降级进程内队列。详见 §10.4 与 `agent-service/app/services/usage_outbox.py`。

前端变更：对话输入区模型选择（Auto + 列表）、设置页「模型」区块（PR4 已实现）、`model` 字段随 SSE 请求发送、错误按新码表展示。

### 9.4 错误码形状与跨端映射（D12 已裁决）

Java 信封（顶层新增可选字段，成功响应不输出）：

```json
{
  "code": 40201,
  "errorType": "quota_exceeded",
  "message": "今日请求额度已用尽，请明日再试",
  "requestId": "..."
}
```

- `code` 仍是数字业务码（不破坏既有端点与前端解析）；`errorType` 是稳定的字符串标识，供跨端映射与前端提示分流。
- `errorType` **只在错误响应出现**；`data` 机制不变（为空即不输出，错误时不塞业务数据）。
- Agent 侧薄映射（`app/services/control_plane.py` 内的映射函数），不散落到路由：

| Java `code` / HTTP | Agent 对外 `code` | HTTP |
| --- | --- | --- |
| `40201` / 429 | `quota_exceeded` | 429 |
| `40202` / 403 | `model_not_available` | 403 |
| `40203` / 422 | `capability_unsupported` | 422 |
| `40216` / 401 | `credential_revoked` | 401 |
| `40215` / 409 | `credential_lease_consumed` | 409 |
| `40218` / 409 | `lease_not_byok` | 409 |
| `40219` / 422 | `credential_rejected` | 422 |
| `40217` / 502 | `upstream_error` | 503 |
| `50001` / 503 或网络失败 | `control_plane_unavailable` | 503 |
| 未知码 | `upstream_error` | 503 |

> 上述 Java 码已在 PR1 的 `ModelErrorCode` 定稿（`40201`–`40208`），PR4 扩展至 `40214`，PR5 再扩展至 `40219`（BYOK lease 与真实验证，完整清单见 `docs/api-contract.md` §8）；`errorType` 字符串一经发布不得改名。

### 9.5 用量查询与对账（PR6 已实现）

**查询接口**：`GET /api/v1/users/me/model-usage`，契约见 `docs/api-contract.md` §5.4。

| 项 | 规则 |
| --- | --- |
| 归属 | 用户只取令牌 `sub`，归属条件下推到 SQL；不提供按用户 ID 查询的入口 |
| 额度快照 | UTC 当日；无额度行时 `used=0`、`limit` 取 `MODEL_QUOTA_DAILY_REQUESTS`、`resetAt` 为次日 00:00Z |
| 明细 | 按 `occurred_at` 倒序分页；`from`/`to` 为闭区间自然日，SQL 用 `[from 00:00Z, to+1 00:00Z)` 半开区间 |
| 分页 | `page ≥ 1`、`size` 1..100；越界与 `from > to` 返回 400 `10001` |
| 关闭 | 运行时总开关关闭返回 404 `40204`，与其余控制面端点一致 |
| 敏感字段 | 不明文回显凭证；台账本身不存提示词、对话内容与密钥 |

**对账（只读，不改台账）**：

| 项 | 规则 |
| --- | --- |
| 定时任务 | `@Scheduled(cron = MODEL_RECONCILE_CRON, zone = "UTC")`，默认 `0 5 0 * * *`（UTC 00:05）；`MODEL_RECONCILE_ENABLED=false` 时跳过 |
| 统计日期 | **前一 UTC 自然日**：00:05 UTC 触发时当日刚开始，统计当日必然为空 |
| 严重项（`ERROR`） | 额度溢出（`used_count > limit_count`）、明细归属或凭证来源与任务不一致 |
| 告警项（`WARN`） | 额度用满（`used_count >= limit_count`）、费用估算为负 |
| 日志 | 只输出计数与日期，不输出用户标识，避免告警通道泄露用户维度信息 |
| 手工脚本 | `scripts/reconcile-model-usage.ps1`，默认对账前一 UTC 自然日（`-DaysBack` 可调），严重项退出码 1；归属与费用为全表复核；同时连接 `postgres` 与 `pgvector`，把 `usage_outbox.dead` 按 `invocation_id` 回查 Java 台账（`-MaxDeadSample` 限制抽样，默认 500）；脚本以 UTF-8 BOM 保存，兼容 Windows PowerShell 5.1 |

## 10. 运行期解析、缓存与失败策略（PR2 已实现；BYOK 调用分支 PR5 已实现）

### 10.1 解析顺序

```text
请求 model（单次覆盖） > 会话 model_key > Auto
        │
        ├─ 显式 BYOK → 必须命中用户可用凭证，否则失败（禁止降级）
        └─ Managed/Auto → 平台默认模型
```

### 10.2 Adapter 与缓存（历史：已被 ADR 0008 的 LiteLLM 网关取代）

- `ProviderSpec` 只描述协议与连接参数：`openai-compatible` 用 `OpenAiCompatibleAdapter`（`ChatOpenAI`），`anthropic-messages` 用 `AnthropicAdapter`（`ChatAnthropic`，V22）。
- 缓存键 `(provider_code, model_key, credential_id)`，值为客户端实例 + 版本戳；凭证更新/撤销/过期、模型下架、任务结束时失效。
- 缓存有界（LRU，上限约 64），避免用户长期累积导致内存增长；撤销凭证时按 `credential_id` 精准失效（`invalidate_credential`）。
- 禁止按原始 Key 缓存；禁止跨用户共享 BYOK 实例；Managed 实例可共享。

### 10.3 失败策略（禁止静默切换）

| 场景 | 行为 |
| --- | --- |
| Java 控制面不可达，且请求为 Auto（未指定模型） | 记录 `warning`，显式降级到进程默认模型，SSE 正常 |
| Java 控制面不可达，且请求显式指定模型（Managed 或 BYOK） | 流前 503 `control_plane_unavailable`，不降级 |
| 凭证无效/撤销/过期 | 流前 401/403 语义码，提示用户重新配置 |
| 能力不满足（如工具调用） | 流前 422 `capability_unsupported` |
| 额度超限 | 流前 429 `quota_exceeded`，响应体带 `quota_type`/`limit`/`used`/`reset_at`（见 §9.2） |

流已开始后只能发 `error` 事件，不得改状态码。

### 10.4 使用明细上报：幂等与重试（Round 2 已确认）

| 项 | 规则 |
| --- | --- |
| `invocation_id` | Agent 在每次真实模型调用（含工具循环中的每一次）生成 UUIDv4，写入该次调用的元信息；同一 `invocation_id` 只对应一次调用，重试复用同一个值 |
| 上报时机 | 调用结束后批量入队，不在 SSE 主链路同步等待；`done` 事件先落库再推送，上报与 SSE 完全解耦 |
| 批次 | 单次批量 1..20 条；超过则拆批 |
| 重试 | 可重试错误（网络错误、5xx、429）按退避重排：1s / 5s / 30s / 120s / 300s / 600s / 1800s；累计 `attempts ≥ 8` 或遇 4xx / 未预期异常即转 `dead`，不再自动重试（2026-10-31 由「最多 3 次」升级） |
| 队列 | Postgres `usage_outbox`（Agent 库）：`invocation_id` 主键、`payload` JSONB、`status`（`pending`/`dispatched`/`dead`）、`attempts`、`next_retry_at`、`last_error`；领取用 `UPDATE ... FOR UPDATE SKIP LOCKED RETURNING` 并推进 `next_retry_at` 形成 60s 租约。写库失败才降级为进程内队列（上限 1000，溢出丢最旧并计数），恢复后回到持久化路径；**仍不在 Agent 建业务台账**（D7） |
| 失败语义 | 上报最终失败**不改变** SSE 结果、不向用户报错、不回滚对话；只记日志与指标（D11） |
| 重启丢失 | **已解决（2026-10-31）**：`pending` 记录随进程重启继续投递；`dispatched` 保留 7 天后清理，`dead` 保留待人工排查。对账仍以 Java 台账为准 |
| 去重 | Java 按 `invocation_id` 唯一索引幂等；重复计入 `duplicated`，不重复写库、不重复计费 |
| 字段可空 | `prompt_tokens`/`completion_tokens`/`latency_ms` 拿不到就留空，**禁止填 0 或估算值冒充精确值**。成本由 Java 计算：`ESTIMATED` 有金额与币种，`UNKNOWN` / `BYOK_NOT_BILLED` 金额为空 |

### 10.5 额度原子扣减规则（Round 2 已确认）

| 项 | 规则 |
| --- | --- |
| 单位 | 请求数 / 日（第一版）；不等于 Provider 费用额度 |
| 维度 | 按 `user_id` 统计，不按 `conversation_id`/`thread_id` 统计 |
| 周期 | UTC 自然日，`quota_date = date(now() AT TIME ZONE 'UTC')`；`reset_at` = 次日 00:00:00Z |
| 计数边界 | 通过鉴权、参数校验、会话归属校验，且进入 Agent 执行阶段（`model-tasks` 创建成功）的请求才计入；之后的模型调用失败仍然计入；认证失败、参数非法、会话归属失败、执行前拒绝一律不计 |
| 适用范围 | Managed 与 BYOK 共用同一额度；BYOK 只免 Provider 费用，不免平台请求额度 |
| 原子性 | 单语句 `INSERT ... ON CONFLICT DO UPDATE ... WHERE used_count < limit_count RETURNING`（§8）；返回 0 行即超限，禁止「先查后改」两步 |
| 配置 | `limit_count` 在当日首条记录写入时按配置快照，中途调整次日生效；数值来自配置（`MODEL_QUOTA_DAILY_REQUESTS`），代码中不写死 |
| 超限响应 | 流前 HTTP 429，业务码 `quota_exceeded`，附 `quota_type=daily_requests`、`limit`、`used`、`reset_at` |
| 并发 | 并发请求由数据库行锁保证不超发；测试必须覆盖「N 并发、limit=N」不超卖 |

### 10.6 能力位与请求侧门控（P3，2026-11-07 已实现）

`models.capabilities` 是开放字符串数组，目录是能力位的唯一权威，Agent 与前端都不得按 Provider 推断：

| 能力位 | 语义 | 消费方 |
| --- | --- | --- |
| `text` | 可对话 | 目录展示 |
| `tool_calling` | 支持工具调用 | Agent 绑工具前判断 |
| `reasoning` | 可产生思考，可被 `POST /chat/stream` 的 `reasoning=true` 请求开启 | Java 校验、Agent 门控 |
| `reasoning_visible` | 思考文本经网关归一化为 `reasoning_content`，Agent 转成 SSE `reasoning` 事件，前端可展示 | 前端折叠面板 |

- 两个标记必须分开：OpenAI 推理类模型只计 reasoning tokens、不返回可展示文本，只标 `reasoning`；合成一个布尔会让前端把空面板当成缺陷。
- 能力位下发链路：`models` → `GET /api/v1/models` / `/api/v2/models` / `/internal/v1/model-access/check` / `/internal/v1/model-tasks`（P3 新增）→ Agent `ResolvedRuntime.capabilities`。会话级设置只在校验时经过 `model-access/check`，覆盖不到请求级 `model`，因此门控必须依赖**本次 `model-tasks` 返回的能力位**。
- 门控在 Agent 侧、流建立前完成（`prepare_agent` → `_ensure_reasoning_supported`），缺 `reasoning` 返回 422 `capability_unsupported`，且早于 BYOK 凭证兑换。**不能让 LiteLLM 兜底**：网关 `drop_params: true` 会静默丢弃不支持的参数，用户会看到「已开启思考」但没有任何思考内容，无法归因。
- P3 只做门控，不向网关下发开启参数；各厂商的 `reasoning_effort` / thinking budget 取值待多厂商矩阵实测（P4）后再按 Provider 白名单补，避免把未验证的参数当成已生效能力。
- 目录数据先只标注 P1 真实链路验证过的 `deepseek:deepseek-v4-pro`（V23），其余模型待实测后补；未标注的模型收到 `reasoning=true` 会被明确拒绝，而不是静默不生效。

## 11. PR1–PR6 计划、依赖、验收与回滚

| PR | 范围 | 依赖 | 验收标准 | 回滚 |
| --- | --- | --- | --- | --- |
| PR1 | Java 控制面骨架：V7 `providers`/`models` + 种子；V8 `model_runtime_tasks`；V9 `model_usage_records`；V10 `model_request_quotas`；服务令牌端点；`/internal/v1/model-tasks`（仅 MANAGED，**含额度原子扣减**）；usage 上报（**按 `invocation_id` 幂等**）；`/internal/v1/model-access/check`；`GET /api/v1/models` | 无 | `mvnw verify` 通过；新增接口契约测试与权限测试；`token_use` 过滤生效（service 令牌访问 `/api/v1` 返回 401）；`/internal/v1/**` 经 80 端口不可达；**额度并发测试**（N 并发、limit=N 不超卖）；**UTC 日界测试**（跨 00:00Z 重置）；**usage 幂等测试**（重复 `invocation_id` 只入库一次）；**失败计入测试**（模型调用失败仍占用额度）；**信封 `errorType` 测试**（成功响应不输出、错误响应输出且不落入 `data`）；`docker compose config -q` 通过 | 关闭 `MODEL_RUNTIME_ENABLED`；新表只增不改，保留即可 |
| PR2 | Agent：`llm.py` 改为按 `(provider,model,credential_id)` 缓存；`control_plane.py`；Resolver；`chat.py` 接入 task 创建与 429 透传；usage 异步上报（**`invocation_id` + 有界队列 + 3 次退避重试**）；错误分类 | PR1 | ruff/mypy/pytest（覆盖率 ≥90）通过；模型切换单测证明实例确实更换；Java 不可达时 Managed 显式降级、BYOK 明确失败；**上报失败不改 SSE 结果**（单测断言 SSE 仍 `done`）；**`invocation_id` 每次调用唯一**（工具循环两次调用生成两个 id）；**Token 用量缺失时字段为 `null` 而非 0**；密钥不入 state 与日志（单测断言） | `MODEL_RUNTIME__ENABLED=false` 回退现有单例逻辑 |
| PR3 | 前端：模型选择（Auto + 列表）、会话级保存（调用 `PUT /sessions/{thread_id}/model`）、请求级覆盖、错误文案（含 429 额度）、会话 `model_key` 回显；Agent 侧 `session_meta.model_key` 写入 | PR2 | `lint`/`type-check`/`test` 通过；**重复提交相同 `model_key` 不产生副作用**（幂等）；**单次覆盖后下一轮恢复会话默认**（不持久化）；**非本人会话 404、目录外 403**；刷新后会话选择保留；历史消息不受影响 | 前端停止发送 `model` 字段与 PUT 请求（Agent 侧字段可选，旧行为自动恢复） |
| PR4 | BYOK 连接与凭证：V11 `provider_connections`、V12 `provider_credentials`；AES-GCM 加解密与 `key_version`；CRUD + 掩码；设置页表单 | PR1 | 加解密单测（唯一 nonce、篡改即失败）；任何接口不回显明文；无回读端点；删除后不可再用 | 关闭 `BYOK_ENABLED`；表保留，密文不外泄 |
| PR5（已完成） | 严格一次性 lease（`leased_at` 条件更新，V13 `base_url` 快照）+ Agent lease 客户端与缓存失效 + `GET /models` 探测（404/405/501 退化为最小 chat）+ 多版本密钥环兼容解密 + 存在 ACTIVE 连接即自动判定 BYOK + BYOK 共用每日额度 | PR4、PR2 | lease TTL/重复兑换 409/撤销 401/跨用户 404 测试；真实远程验证写 `last_verified_at`；**BYOK 同样消耗每日请求额度**；Agent ruff/mypy/pytest 全绿；真实 Provider 冒烟已执行（`GET /models` 200、最小 chat 200、无效 Key 401）；Java 直连 E2E 通过（BYOK 任务、lease 重复兑换 409、撤销后 401、MANAGED 判定） | 关闭 BYOK，前端回落 Auto；V13 只加列，存量任务保持 NULL |
| PR6（已完成） | 对账与运营：Managed/BYOK 归属区分复核、`GET /api/v1/users/me/model-usage` 用量查询、额度配置化（`MODEL_QUOTA_DAILY_REQUESTS`）、对账脚本与溢出告警、`MODEL_RECONCILE_*` 定时任务配置 | PR5 | 重复上报不重复计费（回归）；费用归属字段正确；额度数值来自配置、改配置次日生效；用量查询按 `user_id` 只返回本人数据；审计不含密钥；对账按前一 UTC 自然日统计，日志只输出计数 | 关闭上报开关，台账数据保留；`MODEL_RECONCILE_ENABLED=false` 可停用定时对账 |

> PR4 的 `POST /model-connections/{id}/verify` 当时只做密文完整性校验；PR5 已改为**真实远程验证**（解密后调 Provider，写入 `last_verified_at` 并置 `VERIFIED`）。

> 额度表与原子扣减前移到 PR1：任务授权发生在 PR1，若把额度推迟到 PR6，「任务创建成功即计数」的语义需要重写授权路径。

依赖图：`PR1 → PR2 → PR3`；`PR1 → PR4 → PR5 → PR6`（PR3 与 PR4 可并行）。

回滚通用要求：只允许「加表 + 加列 + 加可选字段」，禁止同一发布内删列或改语义；所有开关默认在开发环境开启、生产按需开启。

### 11.1 实施进度（截至 2026-10-31，按单个提交独立 checkout 验证）

| PR | 状态 | 门禁结果 |
| --- | --- | --- |
| PR1 | 已完成 | `mvnw verify` 21 个测试类 / 150 用例全绿；`docker compose config -q` 通过；文档脚本通过 |
| PR2 | 已完成 | ruff / mypy（37 files）全绿；pytest 237 passed、6 skipped、覆盖率 93.21% |
| PR3 | 已完成 | Agent：ruff / mypy 全绿、pytest 245 passed、6 skipped、覆盖率 92.58%；前端：`lint` / `type-check` / `test`（15 files / 116 tests）全绿 |
| PR4 | 已完成 | `mvnw verify` 25 个测试类 / 180 用例全绿（含 AES-GCM 唯一 nonce/篡改失败、无明文回显、删除后 404）；前端 `lint` / `type-check` / `test` 全绿；`docker compose config -q` 与文档脚本通过；V11/V12 已建表 |
| PR5 | 已完成 | Java `mvnw verify` 27 个测试类 / 212 用例全绿（含 lease TTL/重复兑换 409/撤销 401/跨用户 404、多版本密钥环解密、真实验证探测）；Agent ruff / mypy（37 files）全绿、pytest 272 passed、覆盖率 94.20%；前端 `lint` / `type-check` / `test`（17 files / 125 tests）全绿；V13/V14 已建表；真实 Provider 冒烟与 Java 直连 E2E 已通过；2026-10-31 容器链路已验证：经 Nginx 登录 → BYOK 连接 → 对话流（`token`…`done`）→ lease 落库（`leased_at` 非空）→ 用量上报 `BYOK/success` |
| PR6 | 已完成（PR #3） | Java `mvnw verify` 29 个测试类 / 220 用例全绿（含用量查询分页/日期半开区间/越权归属、对账前一 UTC 自然日统计）；前端 `lint` / `type-check` / `test`（17 files / 125 tests）全绿；文档脚本通过；2026-10-31 已执行对账脚本（真实容器 PostgreSQL，前一 UTC 日与当日均无额度溢出、归属不一致、负费用）；设置页已增加用量面板（额度进度 + 明细分页 + 日期过滤） |

### 11.2 自动审查遗留项（2026-10-31，作为 PR5 输入）

自动审查共发现 1 个严重项与 32 条建议（同类问题在下方合并记录）；严重项与 3 条 PR5 相关建议已在 `99b94f8` 修复（服务令牌口令 fail-fast、`baseUrl` 禁回环/私网、显式模型不降级、`credential_id` 显式失败）。

PR5 期间已处理：V14 清理种子域名、多版本密钥环解密、服务令牌 `sub` 豁免写入规则、`estimatedCost` 之外的 Agent 审查项（图构建前置、`worker.cancel()` await、两处缓存上限、日志断言）、前端事件名/`contextWindow` 可空/UI 文档/两份新增测试。

PR5 后收尾（2026-10-31）：`estimatedCost` 曾加 `@Digits(integer = 6, fraction = 6)` 约束；Agent 侧 `api-reference.md` 补齐 `llm_not_configured` / `llm_provider_unsupported` / `model_runtime_disabled` / `dev_token_unavailable` 四个漏登记错误码，当时的 `configuration.md`（2026-11 已并入 `deployment/environment-variables.md`）已含 `MODEL_RUNTIME__*` 与 `CONTROL_PLANE__*` 全部配置项。**B-07（2026-10-31）后**：`estimatedCost` 已从 Agent→Java 上报契约移除，成本统一由 Java 依据 `model_pricing` 计算，上述 `@Digits` 约束随字段一并废弃。以下为原始清单，仍标注「独立 PR」的属结构性改造，未在本轮处理。

**Java（`application-service`）**

| 问题 | 建议处理 | 时机 |
| --- | --- | --- |
| V7 种子把 `api.openai.com`、`api.deepseek.com` 写死为默认 `base_url` | 种子只保留 provider 与能力；地址由连接或配置决定 | PR5 |
| `ProviderCredentialCipher` 不支持解密旧 `key_version`，与注释「兼容解密」不符 | 实现多版本密钥映射，或修正注释并在轮换前补齐 | PR5 |
| `ServiceTokenService` 的 `sub` 为 `agent-service`，不符合「`sub` 必须是用户 UUID」规则 | 服务令牌豁免写入契约与规则，避免例外失控 | PR5 |
| 两个列表端点返回全量数组，未按统一分页约定 | 返回 `list/total/page/size`，属破坏性变更，放 v2 | **已实现（v2，2026-10-31）**：`GET /api/v2/models`、`GET /api/v2/model-connections`；v1 全量数组保留兼容 |
| 用量上报 `estimatedCost` 缺小数位约束，可能撞 `NUMERIC(12,6)` | 加 `@Digits(integer = 6, fraction = 6)` | 已废弃（B-07 已从上报契约移除该字段，改由 Java 按定价表计算） |
| 测试类使用 `@Autowired` 字段注入 | 改构造器注入；MockMvc 集成测试的字段注入需注明豁免理由 | 已完成（PR6，10 个测试类；无豁免） |

**Agent（`agent-service`）**

| 问题 | 建议处理 | 时机 |
| --- | --- | --- |
| 图实例构建在 `try` 之外，运行时不可用会中断流而非发 `error` 事件 | 移入响应流或前置为可失败步骤，保证 `error` 事件 | PR5 |
| `_event_stream`（69 行）与 `call_model`（65 行）超 50 行，SSE 循环嵌套 4 层 | 抽出 emit 工具函数，降低嵌套 | 已完成（PR9，`_event_stream` 49 行、`call_model` 27 行） |
| `app/api/v1/sessions.py` 路由内自行编排归属校验、目录查询与写库 | 下沉到 service 层 | 已完成（PR10，编排位于 `app/services/session_model.py`） |
| `model_usage` 的 `worker.cancel()` 未 `await` | 改为 `await worker.cancel()` 并处理异常 | PR5 |
| 模型目录与图实例两处缓存无容量上限 | 加容量上限或 TTL | PR5 |
| 新增错误码未同步 `docs/services/agent-service/api-reference.md` | 补齐并跑 `check-doc-links` | PR5 |
| `MODEL_RUNTIME__*`、`CONTROL_PLANE__*` 未同步 `docs/services/agent-service/configuration.md` | 补齐并跑 `check-env-docs` | 已完成（PR5 后统一收敛到 `docs/deployment/environment-variables.md`，该文件不存在也不需要；`MODEL_RUNTIME__ENABLED` 已进 `agent-service/.env.example`） |
| 缺「Token / API Key 不进日志」的断言 | 用 `caplog` 覆盖 chat 与 control_plane 两条路径 | PR5 |

**前端（`frontend`）**

| 问题 | 建议处理 | 时机 |
| --- | --- | --- |
| `src/stores/agent-chat.ts` 677 行，超 300 行门禁 | 拆为会话、流式、模型选择三个 store 或子模块 | 已完成（PR7，拆为 5 个模块，store 245 行，公开接口不变） |
| `views/settings/sections/ModelSection.vue` 248 行，承担加载/表单/列表/操作四类职责 | 拆为表单组件与列表组件 | 已完成（PR6，拆出 ModelConnectionForm / ModelConnectionList） |
| `ChatHeader` 自定义事件声明为 `update:model` 而非 `update:modelValue` | 统一为 `update:modelValue` | PR5 |
| 两处硬编码中文 toast 文案 | 迁入 `locales/zh-CN.ts` 与 `en-US.ts` | 已完成（PR8，新增 `chat.model.switchFailed` / `persistFailed`） |
| 前端 `contextWindow: number` 与 Java `Integer` 可空不一致 | 改 `number \| null` 并处理展示 | PR5 |
| `ModelSelector` 同时写 32px 与 26px 两套高度，使用 11px 任意字号 | 统一取 Token 阶梯高度与字号 | 已完成（PR8，字号改 `text-xs`，高度统一 `--control-height-sm`） |
| PR3 提交混入约 180 行未被引用的 `admin` 文案 | 随管理端功能单独提交，或删除 | 已完成（PR11，中文/英文各删一整套 `admin` 文案） |
| `docs/services/frontend/ui-design-system.md` 仍写「六类设置表单」 | 更新为七类并补模型分区 | PR5 |
| 新增 `api/modules/model.ts` 与设置组件无单元测试 | 补 `model.spec.ts` 与 `ModelSection.spec.ts` | PR5 |

处理原则：与 PR5 契约、安全或运行时语义相关的项在 PR5 内完成；纯风格与文件拆分项独立 PR，避免与 PR5 改动混在一起。

## 12. 与现有规范的冲突与必须同步的文档

| 冲突点 | 处理 |
| --- | --- |
| `architecture-overview.md` §3 写「Java 与 Agent 之间无服务间调用」 | 新增「Agent → Java 内部只读调用」一条，方向明确为单向；不改变「Java 不调用 Agent」 |
| `api-contract.md` 无 `model` 字段、无内部端点 | PR1/PR2 同步 §6、新增内部契约小节（不对公网暴露）；并登记新错误码 `quota_exceeded`、`model_not_available`、`capability_unsupported`、`control_plane_unavailable` |
| `development-rules.md` §1 影响矩阵无模型条目 | 新增一行：「模型/凭证/额度变更 → Java + Agent + 前端 + 契约文档 + `.env.example`」 |
| Java 错误码为数字，Round 2 要求字符串 `quota_exceeded` | **D12 已裁决**：Java 数字码不变，信封新增顶层可选 `errorType`（仅错误时输出，禁止放入 `data`）；Agent 对外保持字符串码，由薄映射层转换（§9.4）。PR1 同步 `api-contract.md` §3/§8 与 `20-backend-java.md` §4 |
| Java 未校验 `token_use` | PR1 修复并登记为安全整改；此前服务令牌不可启用 |
| `LLMSettings.provider` 允许 `azure_openai` 但被拒 | PR2 一并收敛（删除该字面量或实现），避免配置说谎 |

新增环境变量（已写入 `agent-service/.env.example`；受跟踪的根 `.env.example` 只登记 Java 侧键）：

| 服务 | 键 | 用途 |
| --- | --- | --- |
| Java | `MODEL_RUNTIME_ENABLED` | 控制面总开关（false 时内部端点 404） |
| Java | `BYOK_ENABLED` | BYOK 连接与凭证开关 |
| Java | `INTERNAL_AUTH_CLIENT_ID` / `INTERNAL_AUTH_CLIENT_SECRET` | Agent 的服务身份 |
| Java | `INTERNAL_AUTH_TOKEN_TTL` | 服务令牌有效期（默认 `5m`） |
| Java | `MODEL_CRED_MASTER_KEY` / `MODEL_CRED_KEY_VERSION` | 凭证加密主密钥与当前版本（单版本旧配置兼容） |
| Java | `MODEL_CRED_MASTER_KEYS` | 多版本密钥环，形如 `<version>:<base64>` 逗号分隔；旧版本保留以支持兼容解密（PR5） |
| Java | `MODEL_CRED_VERIFY_TIMEOUT` | 远程验证（`GET /models` / 最小 chat）超时，默认 `5s`（PR5） |
| Java | `MODEL_GATEWAY_BASE_URL` / `MODEL_GATEWAY_MASTER_KEY` | LiteLLM 网关地址与 master key；凭证探测只发 `probe:<provider>`，地址与模型由网关决定（ADR 0008） |
| Java | `MODEL_QUOTA_DAILY_REQUESTS` | 每日请求额度上限（产品配置，禁止代码写死；PR1 引入，PR6 收敛配置化） |
| Java | `MODEL_RECONCILE_ENABLED` | 定时对账开关，默认 `true`；运行时总开关关闭时任务自动跳过（PR6） |
| Java | `MODEL_RECONCILE_CRON` | 对账 cron（按 UTC），默认 `0 5 0 * * *`（每日 00:05 对账前一自然日；PR6） |
| Java | `MODEL_DEFAULT_KEY` | Auto 对应的平台默认模型，格式 `<provider>:<modelKey>`；`MODEL_RUNTIME_ENABLED=true` 时启动期校验其可用，不可用即拒绝启动（`DefaultModelStartupValidator`） |
| Agent | `MODEL_RUNTIME__ENABLED` | 运行期解析开关（false 回退现有单例） |
| Agent | `CONTROL_PLANE__BASE_URL` | Java 内部地址（容器网络服务名） |
| Agent | `CONTROL_PLANE__TIMEOUT_SECONDS` | 控制面超时（默认 5） |
| Agent | `CONTROL_PLANE__CLIENT_ID` / `CONTROL_PLANE__CLIENT_SECRET` | 换取服务令牌 |
| Agent | `LLM__GATEWAY_BASE_URL` / `LLM__GATEWAY_API_KEY` | 模型统一出口；配置网关密钥后所有请求经 LiteLLM，未配置时退化为直连（Solo）。Provider 协议与默认地址由网关负责，Agent 不再维护白名单 |

> 2026-11-01：`deepseek-chat` 已被上游下架，`V17__fix_deepseek_model_catalog.sql` 追加 `deepseek-v4-pro` / `deepseek-flash` 并停用旧行。沿用 `MODEL_DEFAULT_KEY=deepseek:deepseek-chat` 的部署会因启动校验被拒绝启动，需同步改为 `deepseek:deepseek-v4-pro`（或 `deepseek:deepseek-flash`）。

## 13. 决策状态（Round 2）

### 13.1 已确认（Round 1 + Round 2）

| 编号 | 结论 | 落地位置 |
| --- | --- | --- |
| Q1 | 会话级模型存 `session_meta.model_key`（`ADD COLUMN IF NOT EXISTS`，`NULL`=Auto，不存展示名/凭证，单请求覆盖不改持久化） | §8 Agent 表、§9 `PUT /sessions/{thread_id}/model`、PR3 |
| Q2 | 使用明细唯一事实源在 Java；Agent 采集上报、`invocation_id` 唯一、可靠重试、上报失败不误判为调用失败、Token 用量可空不伪造、Agent 暂存不构成第二套台账 | D7/D11、§9.3、§10.4、PR1/PR2 |
| Q3 | 新增 `PUT /sessions/{thread_id}/model`，幂等，校验归属/目录/可用性并返回最新配置；不承担单次覆盖 | §9.1、PR3 |
| Q4 | 额度 = 请求数/日，按 `user_id`、UTC 自然日，进入执行阶段才计数（失败也计入），Managed/BYOK 共用，原子扣减，429 + `quota_exceeded` + `quota_type/limit/used/reset_at`，数值来自配置 | §8 表与 SQL、§9.2、§9.3、§10.5、PR1/PR6 |

### 13.2 已裁决（Round 2 追加）

| 编号 | 结论 | 落地位置 |
| --- | --- | --- |
| C1 | 拒绝改 Java 数字码（方案 b 成本收益不成立）。Agent 专属接口用字符串码，由 Agent 薄 Adapter 映射（方案 c）；Java 核心接口用改良版方案 a：**信封顶层**新增可选 `errorType`，不放 `data`（错误时 `data` 为 `null`，混入字段会让前端状态机无法区分渲染与报错） | D12、§9.4、§12、PR1 |

### 13.3 仍待确认（不在本稿假设）

| 编号 | 待确认 | 影响 | 建议 |
| --- | --- | --- | --- |
| Q5 | 服务令牌签发端点是否放在 `/internal/v1/auth/service-token` | 影响暴露面 | 是；并在 Nginx 加回归测试 |
| Q6 | BYOK 首版 Provider 白名单 | 影响目录种子与验证 | OpenAI、DeepSeek、任一 OpenAI 兼容（`base_url` 可配） |
| Q7 | 凭证验证方式：`GET /models` vs 最小 chat 调用 | 影响 Provider 兼容性 | **已落地（PR5）**：优先 `/models`，404/405/501 时退化为 `max_tokens=1` 的最小 chat |
| Q8 | 同 Provider 是否允许多连接/多凭证 | 影响表设计与 UI | Phase 1 每 Provider 每用户 1 条 |
| Q9 | Java 新模块命名与放置 | 影响模块边界 | `model` 模块（`com.example.agent.model`），不塞入 `identity` |
| Q10 | 管理端是否可编辑 Provider/Model 目录 | 影响管理界面 | Phase 1 只读种子，编辑留到后续 |

## 14. Round 2 评审时未做的事（历史记录）

- 未修改任何代码、数据库或编排（仅修改本设计稿、`docs/README.md` 索引与文档校验脚本白名单）。
- 未执行构建与测试；仅运行两个文档门禁脚本（链接检查、环境变量检查）。
- 未创建 ADR（建议 PR1 立项时补 `docs/adr/0002-agent-to-java-control-plane.md`）。
- 未开始编码；等待下一步评审通过后再拆 PR1 任务清单。
