package com.example.agent.model.infrastructure;

import java.math.BigDecimal;

/**
 * 管理端用量按 Provider 聚合行。
 *
 * @param provider        Provider 代码
 * @param requestCount    调用条数
 * @param promptTokens    输入 Token 合计
 * @param completionTokens 输出 Token 合计
 * @param estimatedCost   估算费用合计，可为空
 * @param currency        费用币种，可为空
 * @param currencyCount   参与估算的币种数量，用于识别多币种不可直接求和
 */
public record AdminUsageProviderRow(
        String provider,
        Long requestCount,
        Long promptTokens,
        Long completionTokens,
        BigDecimal estimatedCost,
        String currency,
        Integer currencyCount) {
}
