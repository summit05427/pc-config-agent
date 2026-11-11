-- 消息级赞踩反馈
--
-- user_id 存 JWT sub（users.public_id），与 pc_build_snapshots 保持一致，不落内部自增主键。
-- message_id 由 Agent 的历史接口与 SSE done 事件给出，格式固定为 {thread_id}:{seq}，
-- 这样刷新或翻页后同一条消息仍能命中同一条评价。
CREATE TABLE message_feedback (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID         NOT NULL,
    thread_id   VARCHAR(64)  NOT NULL,
    message_id  VARCHAR(128) NOT NULL,
    rating      VARCHAR(8)   NOT NULL CHECK (rating IN ('UP', 'DOWN')),
    reason_code VARCHAR(32),
    comment     VARCHAR(500),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    -- 一条消息每人只保留一条评价，重复提交走 upsert 覆盖
    CONSTRAINT uk_message_feedback_user_message UNIQUE (user_id, message_id)
);

COMMENT ON TABLE message_feedback IS '消息级赞踩反馈；user_id 为 JWT sub（users.public_id）';
COMMENT ON COLUMN message_feedback.message_id IS 'Agent 输出的稳定消息标识，格式 {thread_id}:{seq}';
COMMENT ON COLUMN message_feedback.reason_code IS '踩的原因，点赞时为空；取值见 FeedbackReason 枚举';

CREATE INDEX idx_message_feedback_created ON message_feedback (created_at DESC);
CREATE INDEX idx_message_feedback_rating ON message_feedback (rating, created_at DESC);
CREATE INDEX idx_message_feedback_thread ON message_feedback (user_id, thread_id);
