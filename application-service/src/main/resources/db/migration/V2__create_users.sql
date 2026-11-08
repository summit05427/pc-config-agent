-- V2：用户与外部身份绑定
-- 设计要点：
--   1. id 为内部自增主键，只在 Java 库内部使用，绝不对外暴露；
--   2. public_id 是对外唯一标识，写入 JWT 的 sub 与 API 响应；
--   3. roles 用逗号分隔的 TEXT 保存，避免引入关联表；
--   4. password_hash 可空，为后续第三方登录（无本地口令）预留。

CREATE TABLE users (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    public_id     UUID         NOT NULL DEFAULT gen_random_uuid(),
    username      VARCHAR(64)  NOT NULL,
    password_hash VARCHAR(100),
    email         VARCHAR(255),
    roles         TEXT         NOT NULL DEFAULT 'USER',
    status        VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_users_public_id UNIQUE (public_id),
    CONSTRAINT uq_users_username  UNIQUE (username),
    CONSTRAINT uq_users_email     UNIQUE (email)
);

-- 第三方身份绑定：同一用户可绑定多个 provider，同一 provider 身份不可重复
CREATE TABLE user_identities (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id      BIGINT       NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    provider     VARCHAR(32)  NOT NULL,
    provider_uid VARCHAR(191) NOT NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_user_identities_provider_uid UNIQUE (provider, provider_uid)
);

CREATE INDEX idx_user_identities_user_id ON user_identities (user_id);
