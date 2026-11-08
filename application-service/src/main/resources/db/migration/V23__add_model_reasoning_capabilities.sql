-- V23：为模型目录补充思考能力位
-- 设计要点：
--   1. 能力位沿用 capabilities 字符串数组，旧客户端忽略未知值，不破坏 v1/v2 契约；
--   2. `reasoning` 表示模型可产生思考（可被请求开启），`reasoning_visible` 表示
--      网关会把思考文本作为 reasoning_content 下发，前端据此决定是否展示；
--      两者拆开是因为 OpenAI 推理模型只计 reasoning tokens、不返回可展示文本，
--      合成一个布尔会让前端把空面板当成缺陷；
--   3. 只标注已通过真实链路验证的模型：deepseek-v4-pro 实测确认思考先于正文下发；
--      其余厂商待多厂商矩阵实测后再补，避免把目录声明当成已验证事实。
-- 幂等：JSONB 的 ? 判断数组内是否已存在该字符串，重复执行不会追加第二份。

UPDATE models
SET capabilities = capabilities || '["reasoning","reasoning_visible"]'::jsonb
WHERE provider_code = 'deepseek'
  AND model_key = 'deepseek-v4-pro'
  AND NOT capabilities ? 'reasoning';
