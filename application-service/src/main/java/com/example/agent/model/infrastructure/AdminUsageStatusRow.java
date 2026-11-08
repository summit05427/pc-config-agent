package com.example.agent.model.infrastructure;

import java.math.BigDecimal;

/**
 * 管理端用量按成本状态聚合行。
 *
 * @param costStatus    成本状态
 * @param requestCount  调用条数
 * @param estimatedCost 估算费用合计，可为空
 * @param currency      费用币种，可为空
 * @param currencyCount 参与估算的币种数量，用于识别多币种不可直接求和
 */
public record AdminUsageStatusRow(
        String costStatus,
        Long requestCount,
        BigDecimal estimatedCost,
        String currency,
        Integer currencyCount) {
}
