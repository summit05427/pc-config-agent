-- V14：目录种子不再写死第三方域名
-- 设计要点：
--   1. providers 表只保留目录信息，接入地址由「连接」或配置决定；
--   2. 默认地址改为配置项 app.model.provider-default-base-urls，可用环境变量覆盖；
--   3. 存量连接行保存的是创建时快照，不受本迁移影响。

UPDATE providers
SET default_base_url = NULL
WHERE default_base_url IS NOT NULL;

COMMENT ON COLUMN providers.default_base_url IS '历史字段；新连接地址来自 app.model.provider-default-base-urls 配置或用户输入';
