-- V22：扩展 BYOK Provider 目录并引入「用户维度模型」
-- 设计要点：
--   1. providers 是 BYOK 选择器的权威数据源，不再从 models 反推供应商；
--   2. 新厂商模型标记 byok_only：只有用户接入该 Provider 后才出现在模型选择器，
--      避免未配置密钥的用户看到不可用模型；
--   3. Anthropic 使用原生 Messages 协议（anthropic-messages），其余厂商走 OpenAI 兼容端点；
--   4. 默认接入地址仍由 app.model.provider-default-base-urls 配置，不写回数据库。

ALTER TABLE models
    ADD COLUMN byok_only BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN models.byok_only IS '仅当用户接入该 Provider 的 BYOK 连接后才可用的目录项';

-- OpenAI 行在 V21 被整体停用；改为保留目录行、按 byok_only 控制用户可见性
INSERT INTO providers (code, display_name, protocol) VALUES
    ('qwen', 'Qwen', 'openai-compatible'),
    ('volcengine', 'Volcengine', 'openai-compatible'),
    ('gemini', 'Google Gemini', 'openai-compatible'),
    ('anthropic', 'Anthropic Claude', 'anthropic-messages')
ON CONFLICT (code) DO UPDATE
SET display_name = EXCLUDED.display_name,
    protocol = EXCLUDED.protocol,
    enabled = TRUE;

INSERT INTO models (provider_code, model_key, display_name, context_window, capabilities, capability_source, byok_only) VALUES
    ('qwen', 'qwen-plus', 'Qwen Plus', 131072, '["text","tool_calling"]'::jsonb, 'catalog', TRUE),
    ('qwen', 'qwen-max', 'Qwen Max', 32768, '["text","tool_calling"]'::jsonb, 'catalog', TRUE),
    ('volcengine', 'doubao-pro-32k', 'Doubao Pro 32K', 32768, '["text","tool_calling"]'::jsonb, 'catalog', TRUE),
    ('gemini', 'gemini-2.5-flash', 'Gemini 2.5 Flash', NULL, '["text","tool_calling"]'::jsonb, 'catalog', TRUE),
    ('gemini', 'gemini-2.5-pro', 'Gemini 2.5 Pro', NULL, '["text","tool_calling"]'::jsonb, 'catalog', TRUE),
    ('anthropic', 'claude-3-5-haiku-latest', 'Claude 3.5 Haiku', NULL, '["text","tool_calling"]'::jsonb, 'catalog', TRUE),
    ('anthropic', 'claude-3-5-sonnet-latest', 'Claude 3.5 Sonnet', NULL, '["text","tool_calling"]'::jsonb, 'catalog', TRUE)
ON CONFLICT (provider_code, model_key) DO NOTHING;

-- V7 已种子化的 OpenAI 模型重新启用，但只对已接入 OpenAI 的用户可见
UPDATE models
SET enabled = TRUE,
    byok_only = TRUE
WHERE provider_code = 'openai'
  AND model_key IN ('gpt-4o-mini', 'gpt-4o');

-- DeepSeek 是当前平台托管模型，保持对全部用户可见
UPDATE models
SET byok_only = FALSE
WHERE provider_code = 'deepseek';
