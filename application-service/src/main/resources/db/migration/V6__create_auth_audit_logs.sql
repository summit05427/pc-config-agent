-- V6：认证审计日志
-- 设计要点：
--   1. 只记录事件与定位信息（用户名、IP、User-Agent、请求 ID），不记录口令、Token、Cookie；
--   2. user_id 可空：登录失败时可能对应不存在的账号，用户被删除后保留历史事件；
--   3. 按时间和用户名建索引，管理端列表按时间倒序分页、按用户名精确过滤。

CREATE TABLE auth_audit_logs (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id    BIGINT REFERENCES users (id) ON DELETE SET NULL,
    username   VARCHAR(64)  NOT NULL,
    event      VARCHAR(32)  NOT NULL,
    ip         VARCHAR(45),
    user_agent VARCHAR(255),
    request_id VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN auth_audit_logs.event IS
    '事件类型：login_success / login_failure / refresh_replay / logout / logout_all / password_change / user_disabled / role_changed';
COMMENT ON COLUMN auth_audit_logs.ip IS '客户端 IP（取 X-Forwarded-For 首段，回退 X-Real-IP 与 remoteAddr）';
COMMENT ON COLUMN auth_audit_logs.user_agent IS '客户端 User-Agent，仅用于定位，不含敏感信息';

CREATE INDEX idx_auth_audit_logs_created_at ON auth_audit_logs (created_at DESC);
CREATE INDEX idx_auth_audit_logs_username ON auth_audit_logs (username, created_at DESC);
