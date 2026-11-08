-- V16：模型定价与成本归属
-- 设计要点：
--   1. 定价是运营维护的版本化数据：同一 (provider, model_key) 可有多条记录，
--      按 effective_from 取「调用发生时刻之前最近一条」，保证历史成本可复现；
--   2. 单价单位为「每百万 token」，避免 NUMERIC 精度被小额单价吃掉；
--   3. 用量行新增 cost_status / cost_bearer / currency：
--        ESTIMATED        平台托管模型，已按定价表算出估算费用
--        UNKNOWN          缺少定价或缺少 token 用量，费用未知（不写 0）
--        BYOK_NOT_BILLED  用户自带凭证，平台不承担费用，也不估算金额
--      cost_bearer 表明成本由谁承担：PLATFORM（平台）或 USER（用户）；
--   4. 存量行统一回填：MANAGED → UNKNOWN/PLATFORM，BYOK → BYOK_NOT_BILLED/USER，
--      不猜测任何金额。

CREATE TABLE model_pricing (
    id                         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider                   VARCHAR(32)    NOT NULL,
    model_key                  VARCHAR(64)    NOT NULL,
    currency                   CHAR(3)        NOT NULL DEFAULT 'USD',
    input_price_per_million    NUMERIC(18, 6) NOT NULL,
    output_price_per_million   NUMERIC(18, 6) NOT NULL,
    effective_from             TIMESTAMPTZ    NOT NULL,
    created_at                 TIMESTAMPTZ    NOT NULL DEFAULT now(),
    CONSTRAINT uk_model_pricing_version UNIQUE (provider, model_key, effective_from),
    CONSTRAINT ck_model_pricing_non_negative CHECK (
        input_price_per_million >= 0 AND output_price_per_million >= 0
    )
);

COMMENT ON TABLE model_pricing IS '模型定价版本；按调用发生时间取生效版本，历史成本不被后续调价改写';
COMMENT ON COLUMN model_pricing.input_price_per_million IS '每百万输入 token 单价，币种见 currency';
COMMENT ON COLUMN model_pricing.output_price_per_million IS '每百万输出 token 单价，币种见 currency';

-- 成本计算按 (provider, model_key) 取 occurred_at 之前最近一条，索引覆盖该访问路径
CREATE INDEX idx_model_pricing_lookup
    ON model_pricing (provider, model_key, effective_from DESC);

ALTER TABLE model_usage_records
    ADD COLUMN cost_status VARCHAR(16),
    ADD COLUMN cost_bearer VARCHAR(16),
    ADD COLUMN currency    CHAR(3);

COMMENT ON COLUMN model_usage_records.cost_status IS 'ESTIMATED / UNKNOWN / BYOK_NOT_BILLED；未知不写 0';
COMMENT ON COLUMN model_usage_records.cost_bearer IS 'PLATFORM / USER；BYOK 由用户承担';
COMMENT ON COLUMN model_usage_records.currency IS '估算费用币种；未估算时为空';

-- 单价放开到 6 位小数后，单次费用可能超过原 NUMERIC(12,6) 的 6 位整数位；
-- 扩宽到 18 位整数位，只放大容量，不改变已有数值
ALTER TABLE model_usage_records
    ALTER COLUMN estimated_cost TYPE NUMERIC(18, 6);

UPDATE model_usage_records
SET cost_status = CASE
        WHEN credential_source = 'BYOK' THEN 'BYOK_NOT_BILLED'
        ELSE 'UNKNOWN'
    END,
    cost_bearer = CASE
        WHEN credential_source = 'BYOK' THEN 'USER'
        ELSE 'PLATFORM'
    END
WHERE cost_status IS NULL;

ALTER TABLE model_usage_records
    ALTER COLUMN cost_status SET NOT NULL,
    ALTER COLUMN cost_bearer SET NOT NULL,
    ADD CONSTRAINT ck_model_usage_cost_status CHECK (
        cost_status IN ('ESTIMATED', 'UNKNOWN', 'BYOK_NOT_BILLED')
    ),
    ADD CONSTRAINT ck_model_usage_cost_bearer CHECK (
        cost_bearer IN ('PLATFORM', 'USER')
    );
