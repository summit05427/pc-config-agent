-- V7：模型目录（Provider / Model）
-- 设计要点：
--   1. Java 是模型目录的唯一权威，Agent 只读取解析结果，不自行探测 Provider 目录；
--   2. 能力元数据用 JSONB 存储，附带来源与验证时间，区分「理论能力」与「已验能力」；
--   3. 首版只读种子，管理端编辑能力留到后续版本。

CREATE TABLE providers (
    code            VARCHAR(32) PRIMARY KEY,
    display_name    VARCHAR(64) NOT NULL,
    protocol        VARCHAR(32) NOT NULL,
    default_base_url VARCHAR(255),
    enabled         BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN providers.protocol IS '通信协议：首版固定 openai-compatible';

CREATE TABLE models (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider_code     VARCHAR(32) NOT NULL REFERENCES providers (code),
    model_key         VARCHAR(64) NOT NULL,
    display_name      VARCHAR(64) NOT NULL,
    context_window    INTEGER,
    capabilities      JSONB       NOT NULL DEFAULT '[]'::jsonb,
    capability_source VARCHAR(32) NOT NULL,
    verified_at       TIMESTAMPTZ,
    enabled           BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uk_models_provider_model_key UNIQUE (provider_code, model_key)
);

COMMENT ON COLUMN models.model_key IS 'Provider 侧稳定模型标识，不含展示名与凭证';
COMMENT ON COLUMN models.capability_source IS '能力来源：catalog 静态目录 / verified 实际验证';
COMMENT ON COLUMN models.verified_at IS '最近一次能力验证时间；为空表示尚未验证';

INSERT INTO providers (code, display_name, protocol, default_base_url) VALUES
    ('openai', 'OpenAI', 'openai-compatible', 'https://api.openai.com/v1'),
    ('deepseek', 'DeepSeek', 'openai-compatible', 'https://api.deepseek.com/v1');

INSERT INTO models (provider_code, model_key, display_name, context_window, capabilities, capability_source) VALUES
    ('openai', 'gpt-4o-mini', 'GPT-4o mini', 128000, '["text","tool_calling"]'::jsonb, 'catalog'),
    ('openai', 'gpt-4o', 'GPT-4o', 128000, '["text","tool_calling","vision"]'::jsonb, 'catalog'),
    ('deepseek', 'deepseek-chat', 'DeepSeek Chat', 65536, '["text","tool_calling"]'::jsonb, 'catalog');
