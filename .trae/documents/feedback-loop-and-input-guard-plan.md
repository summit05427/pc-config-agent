# 反馈闭环 + 输入侧护栏与限流 实施方案

## Context

当前 Agent 在输出侧已有护栏（数字/价格/渠道过滤）、HITL 门控和内部令牌边界；但有两项缺口：

1. **反馈闭环缺失**：消息只有「复制」与「重新生成」，没有赞/踩，无法知道哪类回答让用户不满意，也无法把真实失败样本沉淀成评测用例。
2. **输入侧护栏与限流缺失**：`ChatRequest.message` 只校验长度（1–4000），提示词注入、异常控制字符可以直接进入模型；接口也没有按用户限流，脚本刷接口会直接放大模型成本。

本方案按「先反馈、后护栏」的顺序落地，两者都不新增第三方依赖。

已确认的四个决策：

| 决策点 | 结论 |
| --- | --- |
| 消息身份 | Agent 历史接口与 SSE `done` 事件新增稳定 `message_id`（`{thread_id}:{seq}`） |
| 护栏命中 | 直接拒绝，422 `input_rejected`，并计指标 |
| 限流默认 | 按登录用户 20 次/分钟，Redis 固定窗口，超限 429 + `Retry-After` |
| 反馈回流 | 管理端导出 CSV + 转换脚本生成 eval 用例草稿 |

---

## 第一部分：反馈闭环

### 1. Agent 契约：稳定 `message_id`

`session_messages` 的主键是 `(user_id, thread_id, seq)`，`seq` 来自 `record_turn` 对整轮消息列表的枚举下标，天然稳定。把它暴露出去即可，无需新增表字段。

| 文件 | 改动 |
| --- | --- |
| `agent-service/app/services/session_store/postgres.py` | 两个窗口查询 `SELECT_WINDOW_ASC_SQL` / `SELECT_WINDOW_DESC_SQL` 增加 `seq`；`read_messages` 返回项补 `message_id = f"{thread_id}:{seq}"` |
| `agent-service/app/services/session_store/memory.py` | 同一返回契约，补 `message_id`，保证测试后端与生产一致 |
| `agent-service/app/services/turn.py` | `_persist_turn` 从最终状态取最后一条 `AIMessage` 的下标，`done` payload 增加 `message_id`（与 `build_result` 同层） |
| `agent-service/app/api/v1/sessions.py` | 历史消息原样透传 `message_id`（`_attach_pending_hitl` 逻辑不变） |

约束：`message_id` 只由上述两处产生，格式固定 `^[A-Za-z0-9_.:-]{1,128}$`，不引入随机 UUID，保证刷新后同一消息命中同一条反馈。

### 2. Java 反馈模块

新迁移 `application-service/src/main/resources/db/migration/V25__create_message_feedback.sql`：

```sql
CREATE TABLE message_feedback (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    thread_id    VARCHAR(64) NOT NULL,
    message_id   VARCHAR(128) NOT NULL,
    rating       VARCHAR(8)  NOT NULL CHECK (rating IN ('UP', 'DOWN')),
    reason_code  VARCHAR(32),
    comment      VARCHAR(500),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uk_message_feedback_user_message UNIQUE (user_id, message_id)
);
CREATE INDEX idx_message_feedback_recent ON message_feedback (created_at DESC);
CREATE INDEX idx_message_feedback_rating ON message_feedback (rating, created_at DESC);
CREATE INDEX idx_message_feedback_thread ON message_feedback (user_id, thread_id);
```

新包 `application-service/src/main/java/com/example/agent/feedback/`，按现有 `pcbuild` 的分层放置：

| 层 | 内容 |
| --- | --- |
| `domain` | `FeedbackRating`（UP/DOWN）、`FeedbackReason`（枚举：`INACCURATE` / `OFF_TOPIC` / `INCOMPLETE` / `FORMAT` / `UNSAFE` / `OTHER`）、`FeedbackErrorCode`（`404xx` 区间） |
| `application` | `MessageFeedbackService`：upsert、删除、按会话查询本人反馈、管理端分页与统计、CSV 导出 |
| `infrastructure` | `MessageFeedbackMapper` + `MessageFeedbackRow`，XML 放 `src/main/resources/mapper/feedback/MessageFeedbackMapper.xml` |
| `web` | `MessageFeedbackController`（用户侧）、`AdminFeedbackController`（管理端）、`web/dto/*` |

接口（用户侧，均从 `Authentication.getName()` 解析本人，禁止按 ID 读他人）：

- `PUT /api/v1/messages/{messageId}/feedback`：body `{ threadId, rating, reasonCode?, comment? }`，`ON CONFLICT (user_id, message_id) DO UPDATE`，一条消息只保留一条评价。
- `DELETE /api/v1/messages/{messageId}/feedback`：取消评价（点同一按钮再点一次）。
- `GET /api/v1/feedback?threadId=...`：返回本人该会话的 `[{ messageId, rating, reasonCode }]`，用于刷新后恢复高亮。

接口（管理端，`/api/v1/admin/feedback` 已被 `SecurityConfig` 的 `ADMIN` 规则覆盖，无需改安全配置）：

- `GET /api/v1/admin/feedback`：`PageQuery` + 筛选 `rating` / `reasonCode` / `userId` / `threadId` / `from` / `to`，联表 `users` 返回 `username`。
- `GET /api/v1/admin/feedback/summary`：同一筛选条件下的赞/踩总数、按原因分组计数。
- `GET /api/v1/admin/feedback/export`：同筛选条件导出 CSV（UTF-8 BOM，`Content-Disposition: attachment`）。

边界与校验：

- 不与 Agent 做存在性校验（Java 不得调用 Agent），归属边界是「反馈行属于提交者本人」；`messageId` / `threadId` 用正则与长度校验，SQL 全部参数化。
- 表内不存对话正文，避免把 Agent 的 `session_messages` 复制成第二份事实源。
- `comment` 走长度校验（≤500），不参与任何 HTML 渲染（管理端按纯文本展示）。

### 3. 前端赞踩

| 文件 | 改动 |
| --- | --- |
| `frontend/src/features/sessions/api/types.ts` | `SessionMessage` 增加 `message_id`（可选，兼容旧数据） |
| `frontend/src/features/chat/runtime/history-messages.ts` | 优先用 `item.message_id` 作为 `RuntimeMessage.id`，缺失时回退现有 `history:...` 规则 |
| `frontend/src/features/chat/runtime/types.ts` | `RuntimeMessage` 增加 `feedback?: { rating: 'UP' \| 'DOWN'; reasonCode?: string } \| null` |
| `frontend/src/features/feedback/api/feedback.ts`（新建） | 复用 `@/core/http`，封装 upsert / delete / 按会话查询 |
| `frontend/src/features/chat/components/message-feedback.tsx`（新建） | 赞/踩两个图标按钮 + 点踩后展开原因选择与备注输入；再次点击取消 |
| `frontend/src/features/chat/components/message-item.tsx` | 在现有操作区（复制/重新生成/重试旁）挂载 `MessageFeedback`，仅对已完成的助手消息展示 |
| `frontend/src/i18n/index.ts` | 补 `chat.feedback.*` 文案（中文 + 英文） |

交互约定：乐观更新并高亮；请求失败回滚并 toast；同一个 `message_id` 只显示一个选中态。历史加载后按 `threadId` 拉一次反馈并合并到消息模型。

### 4. 管理端反馈页

| 文件 | 改动 |
| --- | --- |
| `admin/src/features/feedback/types.ts`、`api/admin-feedback-api.ts`、`components/feedback-page.tsx`、`feedback-filters.tsx`、`feedback-table.tsx`、`feedback-summary.tsx` | 新建，结构照抄 `admin/src/features/usage/` |
| `admin/src/routes/_authenticated/feedback/index.tsx` | 新建路由，`validateSearch` 与 usage 页一致 |
| `admin/src/lib/query-keys.ts` | 增加 `adminFeedback` 键族 |
| `admin/src/components/layout/data/sidebar-data.ts` | 运营管理组增加「用户反馈」入口（`MessageSquareWarning` 图标） |

页面内容：顶部统计卡（赞/踩总数、踩占比、Top 原因）、筛选栏（评分、原因、时间范围、用户）、分页表格（时间、用户、会话、消息 ID、评分、原因、备注）、导出按钮。

### 5. 反馈回流评测

新建 `scripts/feedback/export_eval_cases.py`，用 `uv --directory agent-service run python ../../scripts/feedback/export_eval_cases.py` 执行：

1. 读管理端导出的 CSV（`--csv`）；
2. 按 `(userId, threadId, seq)` 关联 Agent 库 `session_messages`，取该消息及其上一条用户提问（`--agent-db`）；
3. 生成草稿到 `agent-service/evals/cases-pending/feedback-YYYYMMDD.yaml`。

不在 `evals/cases/` 下直接生成：`evals/schema.py` 要求 `expect` 至少含一个真实断言，自动填断言等于编造期望。草稿文件头写明「补齐 expect 后手工移入 `cases/` 才会被加载」，`expect` 位置留注释模板。脚本只读，不写 Agent 业务库。

---

## 第二部分：输入侧护栏 + 速率限制

### 1. 配置项

`agent-service/app/core/config.py` 在 `HitlSettings` 之后、`Settings` 之前新增两个配置类：

- `GuardSettings`（前缀 `GUARD__`）：`enabled: bool = True`、`max_input_chars: int = 4000`、`block_on_injection: bool = True`。
- `RateLimitSettings`（前缀 `RATE_LIMIT__`）：`enabled: bool = True`、`chat_per_minute: int = 20`、`window_seconds: int = 60`、`fail_open: bool = True`。

并在 `Settings` 中挂载 `guard` / `rate_limit`。同步 `agent-service/.env.example` 与 `docs/deployment/environment-variables.md`（`scripts/check-env-docs.ps1` 会做双向比对，缺一即失败）。

### 2. 输入护栏

新建 `agent-service/app/services/input_guard.py`，纯函数 + 指标，不做 I/O：

- 规则：`too_long`（超 `max_input_chars`）、`control_chars`（除 `\n\t` 外的 C0/C1）、`zero_width`（零宽/Bidi 控制符）、`injection`（高置信度特征，如「忽略之前的所有指令」「ignore previous instructions」「输出系统提示词」「jailbreak」）。
- 注入特征写成模块常量并配注释：只收高置信度模式，宁可漏检也不误杀正常提问（因为命中即拒绝）。
- 命中返回违规规则名列表；调用方抛 `AppError("输入包含不被支持的内容，请调整后重试", code=CODE_INPUT_REJECTED, status_code=422)`。
- 指标：`app/core/metrics.py` 增加 `INPUT_GUARD_VIOLATIONS = Counter("agent_input_guard_violations_total", ..., ["rule"])`，参照现有 `OUTPUT_GUARD_VIOLATIONS`。
- 日志只记录 `rule`、输入长度、`request_id`，禁止打印用户原文。

`app/core/error_codes.py` 增加 `CODE_INPUT_REJECTED = "input_rejected"`。

### 3. 限流

新建 `agent-service/app/services/rate_limit.py`：

- 复用 `app/core/redis.py` 的客户端与 `is_redis_enabled()`；key 形如 `{prefix}:ratelimit:chat:{user_id}:{window_index}`，`INCR` + `EXPIRE`（同一 pipeline），固定窗口。
- 返回 `(allowed, retry_after_seconds)`；超限抛 `AppError(..., code="rate_limited", status_code=429)`。
- Redis 不可用：`fail_open=True` 时放行并记 warning（与既有幂等降级策略一致），`fail_open=False` 时返回 503。
- `app/core/exceptions.py` 的 `AppError` 增加可选 `headers` 字段，异常处理器把它透传给 `JSONResponse`，用于 `Retry-After`。
- 指标：`RATE_LIMIT_REJECTIONS = Counter("agent_rate_limit_rejections_total", ..., ["scope"])`。

### 4. 接入点

`agent-service/app/api/v1/chat.py::stream_chat`，在 `resolve_profile` 之后、`_claim_idempotency` 之前依次执行：

1. `enforce_input_guard(payload.message)`（新回合与 resume 都校验）；
2. `check_rate_limit(current_user.user_id)`。

顺序原因：护栏是纯计算、成本最低且不占用配额；幂等与线程锁都在其后，被拒绝的请求不会污染幂等记录或抢占锁。拒绝发生在流建立前，返回裸 JSON，不进入 SSE。

---

## 契约与文档同步

| 文件 | 内容 |
| --- | --- |
| `docs/api-contract.md` | 新增反馈三组接口、`message_id` 字段、`input_rejected` / `rate_limited` 错误码与 429 语义 |
| `docs/deployment/environment-variables.md` | `GUARD__*`、`RATE_LIMIT__*` 表格行 |
| `agent-service/.env.example` | 同上环境变量 |
| `docs/services/agent-service/architecture.md` | 新增文件与测试计数 |
| `docs/pc-config/testing-and-evaluation.md` | 反馈回流草稿目录与转换脚本用法 |
| `docs/planning/closure-plan.md` | §3 增加 R10（反馈闭环）、R11（输入护栏与限流）关闭依据 |
| `agent-service/tests/contracts/openapi_snapshot.json` | 契约测试失败时按实际响应更新快照，不手改字段 |

## 验证

按顺序执行，全部通过才算完成：

```powershell
uv --directory agent-service run ruff check app tests evals run.py
uv --directory agent-service run mypy
uv --directory agent-service run pytest -q --cov=app --cov-report=term-missing
uv --directory agent-service run python -m evals --fake

cd application-service; .\mvnw.cmd -q verify

corepack pnpm --dir frontend lint:ci
corepack pnpm --dir frontend type-check
corepack pnpm --dir frontend test:coverage
corepack pnpm --dir frontend e2e:critical

corepack pnpm --dir admin lint:ci
corepack pnpm --dir admin type-check
corepack pnpm --dir admin test
corepack pnpm --dir admin build

powershell -File scripts/check-env-docs.ps1
powershell -File scripts/check-doc-links.ps1
```

新增测试至少覆盖：

- Agent：护栏四条规则（含中文误杀反例）、限流放行/超限/Redis 不可用降级、`done.message_id` 与历史 `message_id` 一致性、`input_rejected` 与 `rate_limited` 在流建立前返回。
- Java：upsert 覆盖、取消、跨用户不可见、分页筛选、CSV 导出、非法 `messageId`。
- 前端：赞/踩点击后高亮与取消、失败回滚、历史 `message_id` 映射。
- 管理端：表格渲染与筛选、统计卡、导出按钮调用。

## 风险与边界

1. `message_id` 是新增契约字段：旧客户端忽略即可，新前端在字段缺失时回退旧 ID 逻辑，不破坏历史数据。
2. Java 无法验证 `message_id` 是否真属于该用户的消息，只保证反馈行归属提交者；管理端展示异常 ID 时按原样显示，不做内容推断。
3. 注入特征是启发式规则，必然存在误杀/漏检；因此只保留高置信度模式，并提供 `GUARD__ENABLED` 作为紧急关闭开关（关闭后不再拦截，指标也不计）。
4. 限流是单实例固定窗口，存在窗口边界双倍突刺；本期不引入令牌桶，避免增加 Lua 脚本与时钟同步复杂度。
5. 反馈表只存评价元数据，不做失败样本自动入库；评测草稿仍需人工补断言后移入 `evals/cases/`。
