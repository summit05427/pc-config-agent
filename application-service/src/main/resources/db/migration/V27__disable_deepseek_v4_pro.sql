-- V27：DeepSeek 只保留 V4.1 Flash
-- 背景：v4-pro 单次结构化调用实测约 50s，多 Agent 串行会把单轮推到 3 分钟以上，
-- 与演示目标冲突；产品侧决定 DeepSeek 仅提供 V4.1 Flash。
-- 不删除历史行：用量明细通过 (provider, model_key) 引用模型，删除会丢失归属。
-- Flash 同时补思考能力位：V23 只标注了 v4-pro，移除该选项后若不补齐，
-- 前端开启 reasoning 会被能力门控拒绝。

UPDATE models
SET enabled = FALSE
WHERE provider_code = 'deepseek'
  AND model_key = 'deepseek-v4-pro';

UPDATE models
SET enabled = TRUE,
    display_name = 'DeepSeek 4.1 Flash',
    capabilities = capabilities || '["reasoning","reasoning_visible"]'::jsonb
WHERE provider_code = 'deepseek'
  AND model_key = 'deepseek-flash'
  AND NOT capabilities ? 'reasoning';
