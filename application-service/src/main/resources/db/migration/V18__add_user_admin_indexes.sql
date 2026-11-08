-- V18：管理端列表查询索引
-- 设计要点：
--   1. 用户列表按 created_at 倒序分页，并为状态过滤补组合索引；
--   2. 审计列表按 event 过滤、按 created_at 倒序分页；
--   3. keyword 使用带前导通配符的 ILIKE，无法命中 B-tree，属管理端低频查询，
--      因此不为它引入 pg_trgm 扩展。

CREATE INDEX idx_users_created_at ON users (created_at DESC);

CREATE INDEX idx_users_status_created_at ON users (status, created_at DESC);

CREATE INDEX idx_auth_audit_logs_event_created_at ON auth_audit_logs (event, created_at DESC);
