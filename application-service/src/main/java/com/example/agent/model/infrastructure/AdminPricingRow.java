package com.example.agent.model.infrastructure;

import java.math.BigDecimal;
import java.time.OffsetDateTime;

/**
 * 管理端定价版本行。
 *
 * <p>比 {@link ModelPricingRow} 多出主键与创建时间，用于管理端列表展示与
 * 「新增后回读」；成本计算仍使用不含主键的轻量行。</p>
 *
 * @param id                    主键
 * @param provider              Provider 代码
 * @param modelKey              模型键
 * @param currency              币种
 * @param inputPricePerMillion  每百万输入 token 单价
 * @param outputPricePerMillion 每百万输出 token 单价
 * @param effectiveFrom         生效时间（UTC）
 * @param createdAt             创建时间（UTC）
 */
public record AdminPricingRow(
        Long id,
        String provider,
        String modelKey,
        String currency,
        BigDecimal inputPricePerMillion,
        BigDecimal outputPricePerMillion,
        OffsetDateTime effectiveFrom,
        OffsetDateTime createdAt) {
}
