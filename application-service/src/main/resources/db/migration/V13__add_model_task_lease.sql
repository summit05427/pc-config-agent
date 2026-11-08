-- V13：运行时任务的一次性凭证兑换标记与 BYOK 接入地址快照
-- 设计要点：
--   1. 凭证兑换是一次性动作，兑换后同一任务不可再次兑换，避免密钥被反复取回；
--   2. 用 leased_at 记录兑换时间，条件 UPDATE（leased_at IS NULL）兜底并发重复兑换；
--   3. base_url 在任务创建时快照，连接后续被改动或删除也不影响在途任务；
--   4. 只加列不改语义，存量任务保持 NULL，不影响历史对账。

ALTER TABLE model_runtime_tasks
    ADD COLUMN IF NOT EXISTS leased_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS base_url VARCHAR(512);

COMMENT ON COLUMN model_runtime_tasks.leased_at IS '凭证一次性兑换时间；非空表示该任务已兑换过';
COMMENT ON COLUMN model_runtime_tasks.base_url IS 'BYOK 任务创建时的接入地址快照，MANAGED 任务为空';
