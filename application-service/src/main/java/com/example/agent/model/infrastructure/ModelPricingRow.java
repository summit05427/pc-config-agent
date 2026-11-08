package com.example.agent.model.infrastructure;

import java.math.BigDecimal;
import java.time.OffsetDateTime;

/**
 * 模型定价版本行。
 *
 * <p>同一 {@code (provider, modelKey)} 可有多条版本记录，调用方按
 * {@code effectiveFrom} 选择「调用发生时刻之前最近一条」。</p>
 *
 * @param provider              Provider 代码
 * @param modelKey              模型键（不含 Provider 前缀）
 * @param currency              币种，ISO-4217 三字母
 * @param inputPricePerMillion  每百万输入 token 单价
 * @param outputPricePerMillion 每百万输出 token 单价
 * @param effectiveFrom         生效时间（UTC）
 */
public record ModelPricingRow(
        String provider,
        String modelKey,
        String currency,
        BigDecimal inputPricePerMillion,
        BigDecimal outputPricePerMillion,
        OffsetDateTime effectiveFrom) {
}
