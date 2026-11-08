-- V10：每日请求额度
-- 设计要点：
--   1. 按用户 + UTC 自然日统计，与 conversation/thread 无关；
--   2. limit_count 在当日首条记录写入时快照，中途改配置次日生效；
--   3. 扣减必须单语句原子执行（INSERT ... ON CONFLICT DO UPDATE ... WHERE ... RETURNING），
--      禁止先查后改，避免并发超发。

CREATE TABLE model_request_quotas (
    user_public_id UUID        NOT NULL,
    quota_date     DATE        NOT NULL,
    used_count     INTEGER     NOT NULL DEFAULT 0,
    limit_count    INTEGER     NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_public_id, quota_date)
);

COMMENT ON COLUMN model_request_quotas.quota_date IS 'UTC 自然日';
COMMENT ON COLUMN model_request_quotas.limit_count IS '当日首次请求时按配置快照，次日生效';
