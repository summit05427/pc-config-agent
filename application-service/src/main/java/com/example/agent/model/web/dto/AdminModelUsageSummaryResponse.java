package com.example.agent.model.web.dto;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

/**
 * 管理端用量聚合响应。
 *
 * <p>金额只在单一币种时给出合计；出现多币种时 {@code estimatedCost} 与 {@code currency}
 * 置空，前端展示「多币种」，绝不把不同币种相加成一个虚假的总额。</p>
 *
 * @param from          起始日期（含），可为空
 * @param to            截止日期（含），可为空
 * @param totals        总量指标
 * @param byCostStatus  按成本状态分布
 * @param byProvider    按 Provider 分布，按调用量倒序，最多 20 条
 * @param byModel       按模型分布，按调用量倒序，最多 20 条
 */
public record AdminModelUsageSummaryResponse(
        LocalDate from,
        LocalDate to,
        Totals totals,
        List<CostStatusBreakdown> byCostStatus,
        List<ProviderBreakdown> byProvider,
        List<ModelBreakdown> byModel) {

    /**
     * 总量指标。
     *
     * @param requestCount    调用总条数
     * @param successCount    成功条数
     * @param failureCount    失败条数
     * @param promptTokens    输入 Token 合计
     * @param completionTokens 输出 Token 合计
     * @param totalTokens     Token 总合计
     * @param estimatedCost   估算费用合计；多币种或无估算时为空
     * @param currency        费用币种；多币种或无估算时为空
     * @param estimatedCount  已估算成本的条数
     * @param unknownCostCount 成本未知的条数
     * @param byokNotBilledCount 用户自带凭证未计费条数
     */
    public record Totals(
            long requestCount,
            long successCount,
            long failureCount,
            long promptTokens,
            long completionTokens,
            long totalTokens,
            BigDecimal estimatedCost,
            String currency,
            long estimatedCount,
            long unknownCostCount,
            long byokNotBilledCount) {
    }

    /**
     * 成本状态分布。
     *
     * @param costStatus   成本状态
     * @param requestCount 条数
     * @param estimatedCost 估算费用合计；多币种时为空
     * @param currency     币种；多币种时为空
     */
    public record CostStatusBreakdown(
            String costStatus,
            long requestCount,
            BigDecimal estimatedCost,
            String currency) {
    }

    /**
     * Provider 维度分布。
     *
     * @param provider        Provider 代码
     * @param requestCount    调用条数
     * @param promptTokens    输入 Token 合计
     * @param completionTokens 输出 Token 合计
     * @param totalTokens     Token 总合计
     * @param estimatedCost   估算费用合计；多币种时为空
     * @param currency        币种；多币种时为空
     */
    public record ProviderBreakdown(
            String provider,
            long requestCount,
            long promptTokens,
            long completionTokens,
            long totalTokens,
            BigDecimal estimatedCost,
            String currency) {
    }

    /**
     * 模型维度分布。
     *
     * @param provider        Provider 代码
     * @param modelKey        模型键
     * @param requestCount    调用条数
     * @param promptTokens    输入 Token 合计
     * @param completionTokens 输出 Token 合计
     * @param totalTokens     Token 总合计
     * @param estimatedCost   估算费用合计；多币种时为空
     * @param currency        币种；多币种时为空
     */
    public record ModelBreakdown(
            String provider,
            String modelKey,
            long requestCount,
            long promptTokens,
            long completionTokens,
            long totalTokens,
            BigDecimal estimatedCost,
            String currency) {
    }
}
