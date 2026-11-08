-- V9：模型调用使用明细（唯一事实源）
-- 设计要点：
--   1. Agent 每次真实模型调用生成一个 invocation_id，唯一索引保证幂等去重；
--   2. Token 用量、耗时、费用允许为空：拿不到就留空，禁止填 0 或估算值冒充精确值；
--   3. 不保存对话内容、提示词或凭证，只存计量元数据。

CREATE TABLE model_usage_records (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invocation_id     UUID         NOT NULL,
    task_id           UUID         NOT NULL REFERENCES model_runtime_tasks (id),
    user_public_id    UUID         NOT NULL,
    thread_id         VARCHAR(128) NOT NULL,
    model_role        VARCHAR(32)  NOT NULL,
    provider          VARCHAR(32)  NOT NULL,
    model_key         VARCHAR(64)  NOT NULL,
    credential_source VARCHAR(16)  NOT NULL,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    latency_ms        INTEGER,
    status            VARCHAR(16)  NOT NULL,
    error_type        VARCHAR(64),
    estimated_cost    NUMERIC(12, 6),
    occurred_at       TIMESTAMPTZ  NOT NULL,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uk_model_usage_invocation UNIQUE (invocation_id)
);

COMMENT ON COLUMN model_usage_records.status IS '调用结果：success / failure';
COMMENT ON COLUMN model_usage_records.prompt_tokens IS '可为空：上游未返回用量时不得伪造';

-- 用量查询按用户 + 时间倒序，覆盖 /users/me/model-usage 的过滤与排序
CREATE INDEX idx_model_usage_user_occurred
    ON model_usage_records (user_public_id, occurred_at DESC);
