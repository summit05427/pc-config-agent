-- V21：停用目录中的 OpenAI 模型
-- 背景：
--   1. 本项目当前只提供 DeepSeek 密钥，V7 种子里预留的 openai:gpt-4o / openai:gpt-4o-mini
--      会让模型选择器与 Auto 暴露实际不可用的模型，这些调用也只能得到 400 或成本 UNKNOWN；
--   2. 与 V17 停用 deepseek-chat 的处理方式一致：只把 enabled 置 FALSE，不删除行——
--      历史用量通过 (provider_code, model_key) 归属这些行，物理删除会丢失归属；
--   3. providers 行保留：BYOK 仍允许用户接入任意 OpenAI 兼容端点，只是平台不再提供
--      这两个模型作为可选目录项。
-- 影响：V20 注释中“OpenAI 模型成本仍为 UNKNOWN”随之失效，平台不再产生这些模型的用量。

UPDATE models
SET enabled = FALSE
WHERE provider_code = 'openai';
