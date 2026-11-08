-- V8：运行时任务（模型调用授权凭据）
-- 设计要点：
--   1. 任务是「凭证授权」的唯一凭据，Agent 凭 task_id 才能兑换 BYOK 凭证；
--   2. 主键由应用层生成 UUID，不依赖数据库扩展，便于跨库迁移；
--   3. user_public_id 存 JWT 的 sub（public_id），不落内部自增主键；
--   4. TTL 到期后任务不可再兑换凭证，历史任务保留用于对账。

CREATE TABLE model_runtime_tasks (
    id                UUID PRIMARY KEY,
    user_public_id    UUID         NOT NULL,
    thread_id         VARCHAR(128) NOT NULL,
    requested_model   VARCHAR(64),
    resolved_model    VARCHAR(64)  NOT NULL,
    credential_source VARCHAR(16)  NOT NULL,
    credential_id     UUID,
    status            VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
    expires_at        TIMESTAMPTZ  NOT NULL,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);

COMMENT ON COLUMN model_runtime_tasks.resolved_model IS '解析后的稳定模型标识：<provider_code>:<model_key>';
COMMENT ON COLUMN model_runtime_tasks.credential_source IS '凭证来源：MANAGED（平台密钥）/ BYOK（用户自带）';
COMMENT ON COLUMN model_runtime_tasks.status IS '任务状态：ACTIVE / EXPIRED / REVOKED';

CREATE INDEX idx_model_runtime_tasks_user_created
    ON model_runtime_tasks (user_public_id, created_at DESC);
