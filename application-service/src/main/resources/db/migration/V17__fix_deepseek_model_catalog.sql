-- V17：修正 DeepSeek 模型目录种子
-- 背景：
--   1. V7 种子里的 deepseek-chat 已被上游拒绝（400 unsupported model），真实可用标识为
--      deepseek-v4-pro / deepseek-flash；
--   2. 已合入主干的脚本只可追加不可修改，因此这里新增正确行并停用失效行，
--      不删除历史行——用量明细通过 (provider, model_key) 引用它们，删除会丢失归属。
-- 去重：运维可能已手工补过行，ON CONFLICT 保证迁移可重复执行而不失败。

INSERT INTO models (provider_code, model_key, display_name, context_window, capabilities, capability_source) VALUES
    ('deepseek', 'deepseek-v4-pro', 'DeepSeek V4 Pro', NULL, '["text","tool_calling"]'::jsonb, 'catalog'),
    ('deepseek', 'deepseek-flash', 'DeepSeek Flash', NULL, '["text","tool_calling"]'::jsonb, 'catalog')
ON CONFLICT (provider_code, model_key) DO NOTHING;

UPDATE models
SET enabled = FALSE
WHERE provider_code = 'deepseek' AND model_key = 'deepseek-chat';
