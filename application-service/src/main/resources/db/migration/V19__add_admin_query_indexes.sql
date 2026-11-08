-- V19：管理端用量与连接查询索引
-- 设计要点：
--   1. 管理端用量列表跨用户按 occurred_at 排序分页，已有 idx_model_usage_user_occurred
--      只覆盖「按用户」路径，因此补全量时间索引；
--   2. Provider / 模型过滤常与时间范围组合，补组合索引避免回表后二次排序；
--   3. 模型连接列表按 created_at 倒序分页，并按 Provider + 状态过滤，补两条索引；
--   4. 成本状态与凭证来源是低基数字段，过滤后仍需按时间排序，不为它们单独建索引。

CREATE INDEX idx_model_usage_occurred
    ON model_usage_records (occurred_at DESC);

CREATE INDEX idx_model_usage_provider_model_occurred
    ON model_usage_records (provider, model_key, occurred_at DESC);

CREATE INDEX idx_provider_connections_created
    ON provider_connections (created_at DESC);

CREATE INDEX idx_provider_connections_provider_status
    ON provider_connections (provider_code, status, created_at DESC);
