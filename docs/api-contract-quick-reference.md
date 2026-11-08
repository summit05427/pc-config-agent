# API 契约速查

| 项    | 内容                       |
| ---- | ------------------------ |
| 源文件  | `docs/api-contract.md`   |
| 性质   | 派生速查（权威以源文件为准，冲突时以源文件为准） |
| 核对日期 | 2026-11-03               |

## &#x20;用户端（application-service，浏览器经 Nginx `/api/v1/**` 直连）

| 方法     | 路径                                                | 鉴权           | 用途          | 关键请求字段                                                      | 关键响应字段                                                                                                          |
| ------ | ------------------------------------------------- | ------------ | ----------- | ----------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| POST   | `/api/v1/auth/login`                              | 放行           | 登录并签发双令牌    | `username`、`password`                                       | `accessToken`、`tokenType`、`expiresIn`、`user`；`Set-Cookie: agent_refresh`                                        |
| POST   | `/api/v1/auth/refresh`                            | 放行（凭 Cookie） | 轮换刷新令牌      | 无请求体，读 `agent_refresh`                                      | `accessToken`、`tokenType`、`expiresIn`；轮换 `Set-Cookie`                                                           |
| POST   | `/api/v1/auth/logout`                             | 放行（凭 Cookie） | 登出当前会话      | 无                                                           | 无 `data`；`Set-Cookie` 置 `Max-Age=0`                                                                             |
| GET    | `/api/v1/auth/me`                                 | 需登录          | 当前用户        | 无                                                           | `publicId`、`username`、`roles`                                                                                   |
| GET    | `/api/v1/users/me/profile`                        | 需登录          | 读取本人资料      | 无                                                           | `publicId`、`username`、`displayName`、`email`、`bio`、`roles`、`status`、`createdAt`、`updatedAt`                      |
| PUT    | `/api/v1/users/me/profile`                        | 需登录          | 更新本人资料      | `displayName`、`email`、`bio`                                 | 同 GET，返回更新后资料                                                                                                   |
| PUT    | `/api/v1/users/me/password`                       | 需登录          | 修改本人密码      | `currentPassword`、`newPassword`                             | 无 `data`；撤销除当前 `sid` 外全部刷新会话                                                                                    |
| POST   | `/api/v1/auth/logout-all`                         | 需登录          | 撤销全部会话      | 无                                                           | 无 `data`；清 Cookie                                                                                               |
| GET    | `/api/v1/users/me/sessions`                       | 需登录          | 登录设备列表      | `page`、`size`                                               | `list`（`familyId`、`createdAt`、`lastUsedAt`、`idleExpiresAt`、`absoluteExpiresAt`、`current`）、`total`、`page`、`size` |
| DELETE | `/api/v1/users/me/sessions/{familyId}`            | 需登录          | 撤销指定设备      | 无                                                           | 无 `data`                                                                                                        |
| GET    | `/api/v1/users/me/preferences`                    | 需登录          | 读取偏好        | 无                                                           | `instructions`、`replyLanguage`、`responseStyle`、`useHistory`、`updatedAt`                                         |
| PUT    | `/api/v1/users/me/preferences`                    | 需登录          | 保存偏好        | `instructions`、`replyLanguage`、`responseStyle`、`useHistory` | 同 GET                                                                                                           |
| GET    | `/api/v1/models`                                  | 需登录          | 模型目录（全量）    | 无                                                           | `provider`、`modelKey`、`displayName`、`capabilities`、`contextWindow`                                              |
| GET    | `/api/v1/model-connections`                       | 需登录          | BYOK 连接列表   | 无                                                           | `id`、`provider`、`providerName`、`baseUrl`、`status`、`lastVerifiedAt`、`createdAt`、`credential`                     |
| POST   | `/api/v1/model-connections`                       | 需登录          | 新建 BYOK 连接  | `providerCode`、`baseUrl`、`apiKey`                           | 连接视图；`credential.status=UNVERIFIED`                                                                             |
| POST   | `/api/v1/model-connections/{connectionId}/verify` | 需登录          | 真实探测凭证      | 无                                                           | 连接视图                                                                                                            |
| DELETE | `/api/v1/model-connections/{connectionId}`        | 需登录          | 软删连接与撤销凭证   | 无                                                           | 无 `data`                                                                                                        |
| GET    | `/api/v1/users/me/model-usage`                    | 需登录          | 本人用量与额度     | `page`、`size`、`from`、`to`                                   | `quota`、`list`、`total`、`page`、`size`                                                                            |
| GET    | `/api/v2/models`                                  | 需登录          | 模型目录（分页）    | `page`、`size`                                               | `list`、`total`、`page`、`size`                                                                                    |
| GET    | `/api/v2/model-connections`                       | 需登录          | BYOK 连接（分页） | `page`、`size`                                               | `list`、`total`、`page`、`size`                                                                                    |

## 管理端（`/api/v1/admin/**`，均需 `ADMIN`）

| 方法    | 路径                                                   | 鉴权      | 用途               | 关键请求字段                                                                                                    | 关键响应字段                                                                                                                                                                                                                                                                         |
| ----- | ---------------------------------------------------- | ------- | ---------------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| GET   | `/api/v1/admin/users`                                | `ADMIN` | 用户检索             | `page`、`size`、`keyword`、`status`                                                                          | `list`（`publicId`、`username`、`email`、`roles`、`status`、`createdAt`）、`total`、`page`、`size`                                                                                                                                                                                       |
| PATCH | `/api/v1/admin/users/{publicId}/status`              | `ADMIN` | 启用/禁用用户          | `status`                                                                                                  | 更新后用户摘要；禁用撤销全部刷新会话                                                                                                                                                                                                                                                             |
| PATCH | `/api/v1/admin/users/{publicId}/roles`               | `ADMIN` | 变更角色             | `roles`（`USER`/`ADMIN`，≤10）                                                                               | 更新后用户摘要                                                                                                                                                                                                                                                                        |
| GET   | `/api/v1/admin/audit-logs`                           | `ADMIN` | 认证审计查询           | `page`、`size`、`event`、`username`                                                                          | `list`（`event`、`username`、`ip`、`createdAt`）、`total`、`page`、`size`                                                                                                                                                                                                              |
| GET   | `/api/v1/admin/models`                               | `ADMIN` | 模型目录管理列表         | `page`、`size`、`keyword`、`provider`、`enabled`                                                              | `list`（`provider`、`modelKey`、`displayName`、`contextWindow`、`capabilities`、`capabilitySource`、`verifiedAt`、`enabled`、`providerEnabled`、`latestPricing`）、`total`、`page`、`size`                                                                                                   |
| PATCH | `/api/v1/admin/models/{provider}/{modelKey}/status`  | `ADMIN` | 启停模型             | `enabled`                                                                                                 | 更新后模型摘要                                                                                                                                                                                                                                                                        |
| GET   | `/api/v1/admin/models/{provider}/{modelKey}/pricing` | `ADMIN` | 定价版本列表           | `page`、`size`                                                                                             | `list`（`id`、`currency`、`inputPricePerMillion`、`outputPricePerMillion`、`effectiveFrom`、`createdAt`）、`total`、`page`、`size`                                                                                                                                                       |
| POST  | `/api/v1/admin/models/{provider}/{modelKey}/pricing` | `ADMIN` | 追加定价版本           | `currency`、`inputPricePerMillion`、`outputPricePerMillion`、`effectiveFrom`                                 | 新增定价版本                                                                                                                                                                                                                                                                         |
| GET   | `/api/v1/admin/model-providers`                      | `ADMIN` | Provider 列表（不分页） | 无                                                                                                         | `code`、`displayName`、`protocol`、`defaultBaseUrl`、`enabled`、`modelCount`、`enabledModelCount`                                                                                                                                                                                    |
| PATCH | `/api/v1/admin/model-providers/{code}/status`        | `ADMIN` | 启停 Provider      | `enabled`                                                                                                 | 更新后 Provider 摘要                                                                                                                                                                                                                                                                |
| GET   | `/api/v1/admin/model-usage`                          | `ADMIN` | 全量用量明细           | `page`、`size`、`userId`、`provider`、`modelKey`、`credentialSource`、`costStatus`、`status`、`from`、`to`、`order` | `list`（`invocationId`、`taskId`、`userId`、`username`、`threadId`、`modelRole`、`provider`、`modelKey`、`credentialSource`、`promptTokens`、`completionTokens`、`latencyMs`、`status`、`errorType`、`estimatedCost`、`costStatus`、`costBearer`、`currency`、`occurredAt`）、`total`、`page`、`size` |
| GET   | `/api/v1/admin/model-usage/summary`                  | `ADMIN` | 用量聚合             | `provider`、`modelKey`、`credentialSource`、`from`、`to`                                                      | `totals`、`byCostStatus`、`byProvider`、`byModel`                                                                                                                                                                                                                                 |
| GET   | `/api/v1/admin/model-connections`                    | `ADMIN` | 连接只读视图           | `page`、`size`、`userId`、`provider`、`status`                                                                | `list`（`id`、`userId`、`username`、`displayName`、`provider`、`providerName`、`baseUrl`、`status`、`lastVerifiedAt`、`createdAt`、`credential`）、`total`、`page`、`size`                                                                                                                    |

## 内部接口（Agent → Java，`/internal/v1/**`，不经 Nginx）

| 方法   | 路径                                                   | 鉴权                                         | 用途                                     |
| ---- | ---------------------------------------------------- | ------------------------------------------ | -------------------------------------- |
| POST | `/internal/v1/auth/service-token`                    | 客户端凭据，无需 Bearer                            | 换取服务令牌（`token_use=service`）            |
| POST | `/internal/v1/model-tasks`                           | 服务令牌 + `X-User-Token`；可选 `Idempotency-Key` | 创建模型任务并原子扣减每日额度；响应含 `capabilities` 能力位 |
| GET  | `/internal/v1/model-tasks/{taskId}`                  | 服务令牌                                       | 读取任务；不存在或过期 404 `40206`                |
| POST | `/internal/v1/model-tasks/{taskId}/credential-lease` | 仅服务令牌                                      | 一次性兑换 BYOK 明文凭证                        |
| POST | `/internal/v1/model-access/check`                    | 服务令牌 + `X-User-Token`                      | 校验用户可使用指定模型                            |
| POST | `/internal/v1/model-usage`                           | 服务令牌 + `X-User-Token`                      | 上报单次调用用量                               |

## Agent 端（公网 `/agent/api/v1/**`，Nginx 剥 `/agent` 前缀）

| 方法     | 公网路径                                          | 鉴权    | 用途            | 关键字段                                                                            |
| ------ | --------------------------------------------- | ----- | ------------- | ------------------------------------------------------------------------------- |
| GET    | `/agent/api/v1/health`、`/health/live`         | 无     | 存活探测，不依赖外部服务  | 响应 `status`、`env`、`service`、`redis`                                             |
| GET    | `/agent/api/v1/health/ready`                  | 无     | 就绪探测          | 200 或 503；`dependencies` 细分 checkpointer / redis                                |
| GET    | `/agent/api/v1/metrics`                       | 网关白名单 | Prometheus 文本 | 可配 `X-Metrics-Token`；关闭时 404 `metrics_disabled`                                 |
| POST   | `/agent/api/v1/auth/dev-token`                | 无     | 仅开发环境签发令牌     | 请求 `user_id`、`expires_minutes`；响应 `access_token`、`token_type`、`expires_in`      |
| POST   | `/agent/api/v1/chat/stream`                   | 需登录   | SSE 对话流       | 请求 `message`、`thread_id`、`model`、`reasoning`、`preferences`；可选 `Idempotency-Key` |
| GET    | `/agent/api/v1/sessions`                      | 需登录   | 会话列表          | `thread_id`、`title`、`model_key`、`last_active_at`、`total`、`page`、`size`          |
| PATCH  | `/agent/api/v1/sessions/{thread_id}`          | 需登录   | 重命名会话         | 请求 `title`（1..80）；响应 `thread_id`、`title`                                        |
| PUT    | `/agent/api/v1/sessions/{thread_id}/model`    | 需登录   | 设置会话级模型       | 请求 `model_key`（`null` 为 Auto）；响应 `model_key`、`effective`、`model`、`updated_at`   |
| DELETE | `/agent/api/v1/sessions/{thread_id}`          | 需登录   | 删除会话          | 204；清理元数据、消息与 checkpoint                                                        |
| GET    | `/agent/api/v1/sessions/{thread_id}/messages` | 需登录   | 历史消息          | `role`、`content`、`tool_calls`、`name`、`total`、`page`、`size`、`order`              |

## SSE 事件（`POST /agent/api/v1/chat/stream`）

| event         | data                                | 说明                          |
| ------------- | ----------------------------------- | --------------------------- |
| `token`       | `{"text": "..."}`                   | 增量文本，按序拼接                   |
| `reasoning`   | `{"text": "..."}`                   | 增量思考内容，与 `token` 分离，仅部分模型提供 |
| `tool_call`   | `{"name": "...", "args": {}}`       | 模型发起工具调用                    |
| `tool_result` | `{"name": "...", "preview": "..."}` | 工具结果摘要，`preview` 截断 200 字符  |
| `done`        | `{"thread_id": "..."}`              | 正常结束                        |
| `error`       | `{"code": "...", "message": "..."}` | 流内错误，HTTP 状态已为 200          |

## 统一错误码

| 域     | code                                                                                                                                                | HTTP                 | 含义                                                        |
| ----- | --------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- | --------------------------------------------------------- |
| Java  | `0`                                                                                                                                                 | 200                  | 成功                                                        |
| Java  | `1xxxx`                                                                                                                                             | 400 等                | `10001` 参数不合法、`10005` 方法不支持、`10007` 登录失败限流                |
| Java  | `2xxxx`                                                                                                                                             | 401 / 403            | `20001` 未认证、`20002` 无权限                                   |
| Java  | `3xxxx`                                                                                                                                             | 404 / 409            | `30001` 资源不存在、`30002` 状态冲突                                |
| Java  | `4xxxx`                                                                                                                                             | 400–502              | 业务与模型模块码；源文件仅列示例，未逐一列全（如 `40102`–`40105`、`40201`–`40221`） |
| Java  | `5xxxx`                                                                                                                                             | 500 / 503            | `50000` 系统错误、`50001` 依赖不可用                                |
| Agent | `unauthorized` / `token_expired` / `token_invalid`                                                                                                  | 401                  | 鉴权失败                                                      |
| Agent | `forbidden` / `model_not_available`                                                                                                                 | 403                  | 开发令牌受限 / 模型不存在或不可用                                        |
| Agent | `session_not_found` / `invalid_pagination`                                                                                                          | 404 / 400            | 会话不存在或不属于当前用户 / 分页越界                                      |
| Agent | `duplicate_request` / `request_in_progress` / `lock_not_acquired` / `credential_lease_consumed` / `lease_not_byok`                                  | 409                  | 幂等、并发与凭证兑换冲突                                              |
| Agent | `validation_error` / `capability_unsupported` / `credential_rejected`                                                                               | 422                  | 校验失败（带 `details`）/ 能力不支持 / 凭证被拒                           |
| Agent | `quota_exceeded`                                                                                                                                    | 429                  | 每日额度用尽，响应体附 `quota`                                       |
| Agent | `redis_unavailable` / `llm_not_configured` / `llm_provider_unsupported` / `credential_unavailable` / `control_plane_unavailable` / `upstream_error` | 503 / 422            | 依赖、模型配置与 BYOK 装配不可用                                       |
| Agent | `metrics_disabled` / `metrics_forbidden` / `internal_error` / `http_{status}`                                                                       | 404 / 403 / 500 / 原始 | 指标端点、未捕获异常与框架级错误                                          |

