# 唯一模型出口收敛到 LiteLLM

当前 `application-service` 的 model 模块同时承担业务职责（模型目录、额度、台账、定价、管理端）与基础设施职责（Provider 协议白名单、默认 base URL、凭证探测），`agent-service` 又维护了一套 Provider 适配器与清单。同一个 Provider 概念在三处各有定义，新增或调整一个 Provider 要改三处代码和两份文档，并且没有任何跨 Provider 的故障切换能力。项目仍处于初期，这份重复的成本只会随功能增长放大，因此现在收敛边界。

## 决策

1. **LiteLLM Proxy 是唯一模型出口**。独立部署，镜像固定为 `ghcr.io/berriai/litellm:v1.106.6`，仅内网可达，调用方只有 `agent-service`。Provider 协议、重试、熔断、故障切换、负载均衡、缓存、护栏、请求级日志全部由它承担。
2. **`agent-service` 只说 OpenAI 兼容协议**。删除 `agent-service/app/services/adapters/` 与 Provider 清单，只保留"业务模型标识 → 网关模型名"的映射。
3. **`application-service` 只保留业务语义**，职责划分如下：

| 能力 | 归属 | 说明 |
| --- | --- | --- |
| 身份、权限、JWT 签发 | Java | 不外包 |
| BYOK 凭证加密存储与一次性下发 | Java | 用户资产；网关不持久化用户密钥 |
| 每日请求额度、任务幂等 | Java | 产品规则，与任务创建同事务 |
| 用量台账、定价、对账 | Java | 财务事实源 |
| 模型可见性、上下架、能力元数据 | Java | 业务语义 |
| 出站地址 SSRF 校验 | Java | 安全边界 |
| Provider 协议、默认 base URL、连通性探测 | LiteLLM | 本次要删除的自研代码 |
| 重试、故障切换、缓存、护栏 | LiteLLM | 本次新增的能力 |

4. **BYOK 走请求级凭证**。`agent-service` 通过请求体的 `user_config` 把用户的 `model`、`api_key`、`api_base` 传给网关，网关仅在本次请求内使用，不落库。平台侧不再做协议判断。
   LiteLLM 默认拒绝请求体中的 `user_config`，必须显式开启 `general_settings.allow_client_side_credentials`。该开关的风险由四条约束共同收敛：网关只绑定回环、只有 Agent 与 Java 持有 master key、用户自定义 `api_base` 先经 Java 的 `OutboundHostGuard` 校验、网关出站网络受限。
5. **不使用 LiteLLM 的 virtual key / team / budget**。用户身份以 Java 签发的 JWT 为准，`application-service` 是唯一身份与额度来源，避免出现两套身份和两套额度。
6. **安全红线**：`turn_off_message_logging: true`；网关不持久化对话内容与用户密钥；复用现有 Postgres 但使用独立 schema `litellm`；网关端口只绑定回环；用户自定义 `api_base` 必须先经 Java 校验再下发。

## 不选择 GoModel 的原因

GoModel 的 Provider 凭证只来自环境变量或配置文件，没有"终端用户自带 Provider 凭证"的入口，BYOK 在其上无法成立；管理接口也仍在演进。LiteLLM 支持请求级凭证，能力覆盖更完整。

## Consequences

- **正面**：Provider 相关自研代码整体删除；获得跨 Provider 故障切换、负载均衡、缓存、护栏与请求级观测；未来更换网关只需改一个 base URL。
- **负面**：新增一个生产组件和一个故障点，需要至少两实例并显式配置超时与重试；新增一个数据库 schema；LiteLLM 迭代快，必须锁版本并固定升级窗口。
- **约束**：业务服务内禁止新增协议、重试、路由、缓存类代码；即使暂时自研也必须藏在可替换接口之后；网关不参与任何业务判断。
- **验收**：重构后 `application-service` 的 model 模块代码行数必须下降；一次 MANAGED 请求与一次 BYOK 请求都能成功，且网关日志中不出现 prompt 与响应内容。

## 迁移阶段

P0（本 ADR）→ P1 起网关并验收 → P2 删除 Agent 适配层 → P3 删除 Java 侧网关职责 → P4 统一观测 → P5 清理测试与文档。

状态（2026-11-07）：P0–P3 已完成；P4 已完成（Java 暴露 `/actuator/prometheus`，`deploy/prometheus/prometheus.yml` 统一抓取三端）；P5 已完成，剩余可选项为真实第三方 Provider 的 MANAGED 联调。

## MCP 出口归属（2026-11-07 追加）

**决策**：MCP Server 清单的唯一来源是 LiteLLM 的 `mcp_servers` 配置；`agent-service` 只作为 MCP 客户端连接网关聚合端点 `{LLM__GATEWAY_BASE_URL}/mcp`（可用 `MCP__GATEWAY_URL` 覆盖）。Agent 不再支持多 Server 直连、`stdio` / `sse` 传输与 `mcp-servers.yaml`。

**理由**：模板的核心价值是「新增一个 MCP Server 只改一处」。若 Agent 与网关各存一份清单，必然出现两份配置漂移；把清单收敛到网关后，Agent 侧只剩一个固定地址，鉴权、审计、限流与多 Agent 复用都由网关承担。

**约束**：

1. **Solo 模式不提供 MCP**。Solo 没有网关，`MCP__ENABLED=true` 时因缺少 `LLM__GATEWAY_API_KEY` 告警跳过，不阻断启动；该限制写入 `docs/deployment/solo-mode.md`。
2. **鉴权复用平台密钥**。Agent 用 `LLM__GATEWAY_API_KEY` 作为 `/mcp` 的 Bearer 令牌，不引入第二份凭证；令牌只来自环境变量，不写进任何配置文件。
3. **治理不分家**。超时、重试、输出截断、脱敏、单轮调用上限、工具可见性（`MCP__ALLOWED_TOOLS`）留在 Agent；Server 注册、上游鉴权、Server 级 allow/deny 归网关。理由：网关看不到对话上下文，且 Solo 形态下网关不存在。
4. **超时顺序**：`mcp_servers.<name>.timeout` 必须小于 `MCP__REQUEST_TIMEOUT_SECONDS`，让网关先超时并返回明确错误，Agent 才能按自身策略重试。

**验证（v1.106.6 实测）**：网关 `mcp_servers` 成功加载公共 Server（3 个工具）；`/mcp` 聚合端点用 master key 完成 `initialize` / `tools/list` / `call_tool`；简化后的 Agent 客户端注册为 `mcp__<tool>` 并成功调用（返回 3107 字符）。实测两个边界：网关未注册任何 Server 时 `/mcp` 返回 **403** 而非空列表；网关 `timeout` 设为 8s 时该 Server 因实际耗时 10.3s 被判失败，改为 25s 后成功——印证「网关超时必须小于 Agent 超时，同时要覆盖上游正常耗时」。默认配置中示例 Server 保持注释状态，避免模板一启动就产生公网出站。
