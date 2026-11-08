package com.example.agent.model.web.dto;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * 管理端定价版本响应。
 *
 * @param id                    主键
 * @param currency              币种
 * @param inputPricePerMillion  每百万输入 token 单价
 * @param outputPricePerMillion 每百万输出 token 单价
 * @param effectiveFrom         生效时间（UTC）
 * @param createdAt             创建时间（UTC）
 */
public record AdminModelPricingResponse(
        long id,
        String currency,
        BigDecimal inputPricePerMillion,
        BigDecimal outputPricePerMillion,
        Instant effectiveFrom,
        Instant createdAt) {
}
