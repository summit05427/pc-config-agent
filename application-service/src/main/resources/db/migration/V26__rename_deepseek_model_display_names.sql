-- V26：修正 DeepSeek 模型展示名
-- 背景：目录中的 model_key 是网关侧稳定标识（deepseek-flash / deepseek-v4-pro），
-- 不能改名；用户看到的是 display_name，应与上游当前版本对齐为 4.1 系列。
-- 说明：只改展示名，不影响会话选择、用量归属或定价版本。

UPDATE models
SET display_name = 'DeepSeek 4.1 Flash'
WHERE provider_code = 'deepseek'
  AND model_key = 'deepseek-flash';

UPDATE models
SET display_name = 'DeepSeek 4.1 Pro'
WHERE provider_code = 'deepseek'
  AND model_key = 'deepseek-v4-pro';
