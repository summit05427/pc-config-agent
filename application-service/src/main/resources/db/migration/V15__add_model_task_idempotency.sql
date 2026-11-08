-- V15：运行时任务的幂等键
-- 设计要点：
--   1. 幂等键由调用方（Agent）按「一次对话轮次」生成，同一键的重试必须复用同一个键；
--   2. (user_public_id, idempotency_key) 唯一索引把「只扣一次额度」下推到数据库，
--      应用层只负责把唯一冲突翻译成「返回既有任务」；
--   3. 可空 + 部分唯一索引：不带键的历史请求与存量行完全不受影响，无需回填；
--   4. 键随任务行长期保留，不回收、不复用；幂等窗口以任务 TTL 为准。

ALTER TABLE model_runtime_tasks
    ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(64);

COMMENT ON COLUMN model_runtime_tasks.idempotency_key IS '调用方传入的幂等键；为空表示未启用幂等';

CREATE UNIQUE INDEX IF NOT EXISTS uk_model_runtime_tasks_idem
    ON model_runtime_tasks (user_public_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
