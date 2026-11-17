# 环境变量速查

| 项 | 内容 |
| --- | --- |
| 状态 | Derived（派生视图） |
| 最后更新 | 2026-11-17 |
| 源文件 | [environment-variables.md](./environment-variables.md)、根 `.env.example` |
| 规则 | 与源文件冲突时以源文件为准；变量变更必须同步本文 |

## 1. 必改项（生产）

| 变量 | 默认 | 改成 |
| --- | --- | --- |
| `POSTGRES_PASSWORD` | `replace-with-*` | 强随机口令 |
| `AGENT_POSTGRES_PASSWORD` | `replace-with-*` | 强随机口令 |
| `REDIS_PASSWORD` | `replace-with-*` | 强随机口令，URL 编码 |
| `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` | 占位 | 真实 RSA PEM（单行 `\n`） |
| `JWT_KID` | `rsa-2026-10` | 实际密钥标识 |
| `AUTH_ADMIN_PASSWORD` | `replace-with-*` | 强口令 |
| `INTERNAL_AUTH_CLIENT_SECRET` | `replace-with-*` | ≥ 16 字符 |
| `LITELLM_MASTER_KEY` / `LITELLM_SALT_KEY` | 占位 | ≥ 32 字符 |
| `LLM__GATEWAY_API_KEY` | 占位 | 等于 `LITELLM_MASTER_KEY` |
| `LLM_API_KEY` | 占位 | 真实 provider key（直连/Solo） |

## 2. 最常调

| 需求 | 变量 | 默认 |
| --- | --- | --- |
| 换默认模型 | `MODEL_DEFAULT_KEY`、`LLM_MODEL` | `deepseek:deepseek-flash` |
| 换端口 | `WEB_PORT` / `BACKEND_PORT` / `AGENT_PORT` | `8088` / `8080` / `8000` |
| 开 HITL | `HITL_ENABLED` | `true` |
| 开/关多 Agent | `MULTI_AGENT_ENABLED` / `CRITIC_ENABLED` | `true` / `true` |
| 调 RAG 引用阈值 | `RAG_MIN_RELEVANCE_SCORE` | `0.2` |
| 开 OpenUI | `OPENUI_ENABLED` + `VITE_OPENUI_ENABLED` | `true` |
| RAG 开关 | `RAG_ENABLED` | `true` |
| 模型运行时 / BYOK 开关 | `MODEL_RUNTIME_ENABLED` / `BYOK_ENABLED` | `true` / `true` |
| 关限流 | `RATE_LIMIT_ENABLED` | `true` |
| 调输入上限 | `GUARD_MAX_INPUT_CHARS` | `4000` |
| 调每日额度 | `MODEL_QUOTA_DAILY_REQUESTS` | `100` |
| 调选型修正/检索配额 | `AGENT__ARCHITECT_MAX_PARTIAL_CHECKS` / `MAX_KNOWLEDGE_CALLS` / `MAX_TOKENS` | `3` / `2` / `4096` |

## 3. 开关联动

| 组合 | 约束 |
| --- | --- |
| `BYOK_ENABLED=true` | 必须 `MODEL_RUNTIME_ENABLED=true`，且 `MODEL_CRED_MASTER_KEY` 合法 |
| `HITL_ENABLED=true` | 必须 `STORAGE__BACKEND=postgres` |
| `OPENUI_ENABLED` | 必须与 `VITE_OPENUI_ENABLED` 同值 |
| `RAG_ENABLED=true` | 必须配置 `RAG_RETRIEVER_MODULE` 与成对的 embedding 模型/维度 |
| `MULTI_AGENT_ENABLED=false` | `CRITIC_ENABLED` 不再生效 |
| `MCP_ENABLED=true` | 仅网关拓扑；Solo 不支持 |
| `AUTH_COOKIE_SECURE=false` | 仅非 `prod` 本地调试允许 |

## 4. 生产启动失败速查

| 现象 | 检查 |
| --- | --- |
| Java 启动即退 | `SPRING_PROFILES_ACTIVE`、JWT 私钥、管理员口令、DB 口令是否仍为占位 |
| Agent 启动即退 | Agent 与 Java 的 JWT 配置是否一致；`REDIS__REQUIRED`；HITL/RAG 约束 |
| 401 / 验签失败 | `JWT_ISSUER`、`JWT_AUDIENCE`、`JWT_KID`、公钥是否两端一致 |
| SSE 无输出 | `LLM__GATEWAY_BASE_URL`、`LLM__GATEWAY_API_KEY` 是否正确 |
| 模型 404 | `MODEL_RUNTIME_ENABLED` 与 `MODEL_DEFAULT_KEY` 是否一致 |

## 5. 相关文档

- 完整说明：[environment-variables.md](./environment-variables.md)
- 部署：[deployment-guide.md](./deployment-guide.md)
- Solo：[solo-mode.md](./solo-mode.md)
