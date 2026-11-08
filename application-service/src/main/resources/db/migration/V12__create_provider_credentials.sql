-- V12：Provider 凭证（只存密文）
-- 设计要点：
--   1. 明文密钥只在录入与运行时兑换的内存作用域出现，数据库永远只有密文；
--   2. 密文结构 v1:<key_version>:<base64(nonce|tag|ciphertext)>，由应用层加解密；
--   3. 撤销采用状态位而不是物理删除，便于对账与轮换；同一连接同时只允许 1 条 ACTIVE。

CREATE TABLE provider_credentials (
    id              UUID         PRIMARY KEY,
    connection_id   UUID         NOT NULL REFERENCES provider_connections (id),
    user_public_id  UUID         NOT NULL,
    credential_type VARCHAR(16)  NOT NULL,
    ciphertext      TEXT         NOT NULL,
    key_version     INTEGER      NOT NULL,
    masked_hint     VARCHAR(32)  NOT NULL,
    status          VARCHAR(16)  NOT NULL DEFAULT 'UNVERIFIED',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    revoked_at      TIMESTAMPTZ
);

COMMENT ON COLUMN provider_credentials.credential_type IS '凭证类型：首版固定 api_key';
COMMENT ON COLUMN provider_credentials.ciphertext IS 'AES-256-GCM 密文：v1:<key_version>:<base64(nonce|tag|ciphertext)>';
COMMENT ON COLUMN provider_credentials.key_version IS '加密主密钥版本，用于密钥轮换兼容解密';
COMMENT ON COLUMN provider_credentials.masked_hint IS '掩码提示，如 sk-****abcd；不含完整密钥';
COMMENT ON COLUMN provider_credentials.status IS '凭证状态：UNVERIFIED / VERIFIED / REVOKED';

CREATE UNIQUE INDEX uk_provider_credentials_connection_active
    ON provider_credentials (connection_id)
    WHERE status <> 'REVOKED';

CREATE INDEX idx_provider_credentials_user
    ON provider_credentials (user_public_id);
