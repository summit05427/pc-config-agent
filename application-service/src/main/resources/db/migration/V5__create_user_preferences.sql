-- V5：用户偏好
-- 设计要点：
--   1. 一个用户最多一行，user_id 直接作为主键，用户删除时级联清理；
--   2. 偏好是「客户端声明的用户偏好」，不参与鉴权，只在对话时拼进 system prompt；
--   3. 表没有更新触发器，保存时必须显式写 updated_at = now()（与 V4 的资料更新一致）。

CREATE TABLE user_preferences (
    user_id        BIGINT      PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    instructions   VARCHAR(1000),
    reply_language VARCHAR(16) NOT NULL DEFAULT 'auto',
    response_style VARCHAR(16) NOT NULL DEFAULT 'balanced',
    use_history    BOOLEAN     NOT NULL DEFAULT TRUE,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN user_preferences.instructions IS '自定义指令，空值表示未设置';
COMMENT ON COLUMN user_preferences.reply_language IS '回复语言：auto / zh-CN / en-US';
COMMENT ON COLUMN user_preferences.response_style IS '回复风格：concise / balanced / detailed';
COMMENT ON COLUMN user_preferences.use_history IS '是否把历史消息注入对话上下文';
