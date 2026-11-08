# Solo 模式

| 属性 | 内容 |
| --- | --- |
| 状态 | Current |
| 最后核验 | 2026-11-04 |
| 权威性 | Authoritative（Solo 启动、dev-token、curl 联调与能力边界的唯一入口） |
| 主要证据 | `docker-compose.yml`、`.env.solo.example`、`scripts/generate_solo_env.py`、`agent-service/app/api/v1/auth.py`、`agent-service/app/api/v1/chat.py`、`agent-service/app/core/config.py` |
| 变量登记 | 见 [`environment-variables.md`](environment-variables.md) |

---

## 1. 适用场景与边界

Solo 模式只启动 `agent-service` 一个容器，不启动 Java、管理端、前端与任何中间件，用于模板演示、Agent 单点联调与接入方快速体验。

Solo 下**不可用**的能力（都依赖 Java 控制面或 Postgres / Redis）：

- 模型额度与配额校验；
- BYOK（用户自备密钥）与密钥托管；
- 会话级模型选择（`MODEL_RUNTIME__ENABLED` 保持 `false`，只用进程默认模型）；
- 用量台账与计费；
- 基于 Postgres 的会话持久化（Solo 用 memory 存储，进程重启即丢失）；
- 基于 Redis 的会话锁与幂等记录（Solo 无 Redis，自动降级为不跨实例的进程内实现）；
- MCP 接入（MCP Server 由 LiteLLM 托管，Solo 没有网关，`MCP__ENABLED=true` 也会因缺少 `LLM__GATEWAY_API_KEY` 而告警跳过）。

需要上述能力时改用整栈：`docker compose --profile full up -d --build`（见 [deployment-guide.md](deployment-guide.md) §3.2）。

## 2. 三条命令启动

```powershell
# 1. 生成 .env.solo：本地自签 RSA 密钥对 + memory 存储 + 空 REDIS__URL
uv --directory agent-service run python ../scripts/generate_solo_env.py

# 2. 打开 .env.solo，把 LLM_API_KEY 换成真实密钥（其余变量保持默认）

# 3. 只构建并启动 Agent
docker compose --env-file .env.solo up -d --build agent-service
```

`agent-service` 不带 Compose profile，因此 `docker compose up -d --build` 在不启用 profile 时也只会启动它；显式写服务名更直观。

- `.env.solo` 由脚本生成，含真实本地密钥，已在 `.gitignore` 中排除；模板 `.env.solo.example` 随仓库提交。
- 生成脚本生成 RSA 2048 密钥对，以单行 PEM（`\n` 字面量）写入 `AUTH__DEV_PRIVATE_KEY` 与 `AUTH__JWT_PUBLIC_KEY`，二者成对，不可单独替换。
- 已存在 `.env.solo` 时脚本拒绝覆盖；确需重新生成加 `--force`。
- 健康检查：`curl http://127.0.0.1:8000/api/v1/health/ready` 返回 200。
- 停止：`docker compose --env-file .env.solo stop agent-service`；清理：`docker compose --env-file .env.solo down`。

## 3. 获取开发令牌

`/api/v1/auth/dev-token` 只在 `APP_ENV=dev` 且 `DEBUG=true` 时可用，Solo 默认即满足；生产环境返回 403 或 503。

```bash
TOKEN=$(curl -sS -X POST http://127.0.0.1:8000/api/v1/auth/dev-token \
  -H "Content-Type: application/json" \
  -d '{"user_id":"solo-user"}' | python -c "import json,sys;print(json.load(sys.stdin)['access_token'])")
```

返回体为 `{"access_token": "...", "token_type": "Bearer", "expires_in": 3600}`；`expires_minutes` 可覆盖有效期（1–1440）。

## 4. curl 调用流式对话

```bash
curl -N -X POST http://127.0.0.1:8000/api/v1/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"message":"你好，介绍一下你自己","thread_id":"solo-demo-1"}'
```

- `-N` 关闭 curl 缓冲，否则看不到逐字输出。
- 事件依次为 `token`（增量文本）、`done`（结束），异常时为 `error`。
- `thread_id` 由调用方维护，同一值会接着历史上下文；Solo 用 memory 存储，进程重启后历史丢失。
- 可用 `agent_id` 切换到其他 Profile（如 `writer`）；省略则用默认 Profile。

## 5. 与整栈的差异

| 项 | 整栈（`--profile full`） | Solo |
| --- | --- | --- |
| 启动服务 | 四端 + `postgres` / `pgvector` / `redis` | 仅 `agent-service` |
| `APP_ENV` / `DEBUG` | `prod` / `false` | `dev` / `true` |
| 鉴权 | Java 签发 RS256 令牌 | `/api/v1/auth/dev-token` 自签 |
| 存储 | `STORAGE__BACKEND=postgres` | `memory` |
| Redis | 必需 | 关闭（`REDIS__REQUIRED=false`） |

## 6. 常见问题

- **`dev_token_unavailable`（503）**：`.env.solo` 缺 `AUTH__DEV_PRIVATE_KEY`，或该值不是合法 PEM 私钥；重新运行生成脚本。
- **所有请求 401**：`AUTH__DEV_PRIVATE_KEY` 与 `AUTH__JWT_PUBLIC_KEY` 不成对（单独替换了其中一个），重新生成。
- **端口 8000 被占用**：整栈的 `agent-service` 还在运行，先 `docker compose --profile full stop agent-service`。
- **Compose 报某变量缺失**：`.env.solo` 被手工删减或由旧版模板生成。模板中的 `solo-unused` 变量用于满足未启用服务的插值，不能删除；ADR 0008 之后还必须保留 `LITELLM_MASTER_KEY=solo-unused` 与 `LITELLM_SALT_KEY=solo-unused`，否则 `docker compose config` 会在 LiteLLM / Prometheus 的必填校验处失败（Solo 并不启动网关，这两个值不会被使用）。
- **旧版 `.env.solo` 的补救**：不要直接 `--force` 重新生成（会覆盖已有真实密钥），在文件末尾补上上面两行，并显式写入 `LLM_GATEWAY_API_KEY=`（必须为空，否则 Agent 会继承 dummy master key 去连接未启动的 LiteLLM，表现为 `OpenAIConnectionError`）。
