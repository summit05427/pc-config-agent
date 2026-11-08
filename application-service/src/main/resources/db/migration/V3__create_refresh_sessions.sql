-- V3：刷新会话
-- 设计要点：
--   1. token_hash 只存 SHA-256 摘要：库被拖走也无法还原出可用的 Refresh Token；
--   2. family_id 把一次登录派生出的整条轮换链绑定在一起，检测到重放时整族撤销；
--   3. absolute_expires_at 是登录时刻起的硬上限，idle_expires_at 随每次使用向后推移；
--   4. replaced_by_id 指向轮换出的新会话，既是审计线索，也用于区分「正常轮换」与「重放」。

CREATE TABLE refresh_sessions (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id             BIGINT       NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    family_id           UUID         NOT NULL,
    token_hash          CHAR(64)     NOT NULL,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_used_at        TIMESTAMPTZ,
    absolute_expires_at TIMESTAMPTZ  NOT NULL,
    idle_expires_at     TIMESTAMPTZ  NOT NULL,
    revoked_at          TIMESTAMPTZ,
    revoked_reason      VARCHAR(32),
    replaced_by_id      BIGINT       REFERENCES refresh_sessions (id),
    CONSTRAINT uq_refresh_sessions_token_hash UNIQUE (token_hash)
);

-- 按用户清理与「退出所有设备」的过滤列
CREATE INDEX idx_refresh_sessions_user_id ON refresh_sessions (user_id);
-- 重放时按族撤销，必须走索引，避免全表扫描
CREATE INDEX idx_refresh_sessions_family_id ON refresh_sessions (family_id);
