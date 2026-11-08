package com.example.agent.model.infrastructure;

import java.math.BigDecimal;

/**
 * 管理端用量聚合总量行。
 *
 * <p>费用只在 {@code ESTIMATED} 状态下累加；币种数量用于识别「多币种不可直接相加」，
 * 服务层在多于一种币种时把汇总币种置空，而不是给出一个错误的总额。</p>
 */
public record AdminUsageTotalsRow(
        Long requestCount,
        Long successCount,
        Long failureCount,
        Long promptTokens,
        Long completionTokens,
        BigDecimal estimatedCost,
        Integer estimatedCurrencyCount,
        String estimatedCurrency) {
}
