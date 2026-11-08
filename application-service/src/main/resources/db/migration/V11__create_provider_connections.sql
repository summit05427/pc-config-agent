-- V11：用户 Provider 连接（BYOK 配置，不含密钥）
-- 设计要点：
--   1. 连接只描述「哪个用户接入了哪个 Provider、用哪个 base_url」，密钥单独存 V12；
--   2. Phase 1 每 Provider 每用户只允许 1 条 ACTIVE 连接，删除后置 DELETED 并保留历史；
--   3. 部分唯一索引只约束 ACTIVE 行，保证「删除后可重新创建」而不丢审计痕迹。

CREATE TABLE provider_connections (
    id               UUID         PRIMARY KEY,
    user_public_id   UUID         NOT NULL,
    provider_code    VARCHAR(32)  NOT NULL REFERENCES providers (code),
    base_url         VARCHAR(255) NOT NULL,
    status           VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
    last_verified_at TIMESTAMPTZ,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

COMMENT ON COLUMN provider_connections.user_public_id IS '用户公开 ID（JWT sub），不落内部自增主键';
COMMENT ON COLUMN provider_connections.status IS '连接状态：ACTIVE / DELETED';
COMMENT ON COLUMN provider_connections.last_verified_at IS '最近一次上游可用性验证时间；PR4 不写入';

CREATE UNIQUE INDEX uk_provider_connections_user_provider_active
    ON provider_connections (user_public_id, provider_code)
    WHERE status = 'ACTIVE';

CREATE INDEX idx_provider_connections_user_created
    ON provider_connections (user_public_id, created_at DESC);
