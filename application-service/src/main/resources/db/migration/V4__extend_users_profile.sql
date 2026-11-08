-- V4：用户资料字段
-- 设计要点：
--   1. display_name / bio 可空，空值表示「未设置」，前端回退到 username；
--   2. users 没有 updated_at 触发器（V2 只有 DEFAULT now()），保存资料必须在 SQL 中显式写 updated_at = now()；
--   3. email 列与唯一约束已在 V2 存在，无需新增；空串必须在应用层归一化为 NULL 后再写入。

ALTER TABLE users ADD COLUMN display_name VARCHAR(64);
ALTER TABLE users ADD COLUMN bio VARCHAR(500);

COMMENT ON COLUMN users.display_name IS '展示名，空值表示未设置，前端回退到 username';
COMMENT ON COLUMN users.bio IS '个人简介，空值表示未设置';
