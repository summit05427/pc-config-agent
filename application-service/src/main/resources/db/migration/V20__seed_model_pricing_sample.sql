-- V20：示例定价种子（成本估算用，模板不含计费/结算）
-- 背景与口径：
--   1. V16 只建表不供数，模板开箱即用时所有平台托管调用的 cost_status 恒为 UNKNOWN，
--      成本观测链路无法演示；本迁移为在用模型补两条示例定价。
--   2. estimated_cost 是「成本估算」而非应收金额：本模板不接入支付、不做账单、
--      不做余额扣费，成本字段只用于用量观测与对账。
--   3. 来源：DeepSeek 官方价目页 https://api-docs.deepseek.com/quick_start/pricing
--      抓取日期 2026-11-04，币种 USD，单位为每百万 token。
--   4. 官方价区分「峰时/非峰时」与「缓存命中/未命中」，而 model_pricing 只有一个
--      输入单价字段，因此统一取最高档「峰时 + 缓存未命中」作为保守上界；
--      实际费用通常低于估算，替换为真实采购价时请一并更新本注释。
--   5. effective_from 取 2026-01-01，早于任何现有调用时间，避免「有价格但查不到」；
--      ON CONFLICT 保证运营已手工录入同版本价格时不被覆盖，迁移可重复执行。
--   6. 目录中的 openai:gpt-4o / openai:gpt-4o-mini 已由 V21 停用，不再产生平台托管用量，
--      因此这里不为它们供价；如后续重新启用，需同步补价，不在此猜测。

INSERT INTO model_pricing (
    provider,
    model_key,
    currency,
    input_price_per_million,
    output_price_per_million,
    effective_from
) VALUES
    ('deepseek', 'deepseek-flash', 'USD', 0.300000, 1.200000, '2026-01-01T00:00:00Z'),
    ('deepseek', 'deepseek-v4-pro', 'USD', 1.320000, 3.960000, '2026-01-01T00:00:00Z')
ON CONFLICT ON CONSTRAINT uk_model_pricing_version DO NOTHING;
