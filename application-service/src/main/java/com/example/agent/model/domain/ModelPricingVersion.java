package com.example.agent.model.domain;

import java.math.BigDecimal;
import java.time.OffsetDateTime;

/**
 * 模型定价版本快照，用于按调用发生时刻选择生效价格。
 *
 * @param provider               Provider 代码
 * @param modelKey               模型键
 * @param inputPricePerMillion   每百万输入 token 单价
 * @param outputPricePerMillion  每百万输出 token 单价
 * @param currency               币种
 * @param effectiveFrom          生效时间
 */
public record ModelPricingVersion(
        String provider,
        String modelKey,
        BigDecimal inputPricePerMillion,
        BigDecimal outputPricePerMillion,
        String currency,
        OffsetDateTime effectiveFrom) {
}
