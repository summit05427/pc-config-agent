package com.example.agent.model.domain;

/**
 * 模型用量对账结果（只读统计）。
 *
 * @param ran                    本次是否实际执行；运行时关闭时为 {@code false}
 * @param quotaOverflowUsers     对账自然日已用数超过上限的用户数（不应出现）
 * @param quotaAtLimitUsers      对账自然日已用满额度的用户数
 * @param attributionMismatches  明细与任务归属不一致的条数（不应出现）
 * @param negativeEstimatedCost  费用估算为负数的条数
 * @param costStatusMismatches   成本状态与金额/币种不一致的条数（不应出现）
 */
public record ReconciliationResult(
        boolean ran,
        int quotaOverflowUsers,
        int quotaAtLimitUsers,
        int attributionMismatches,
        int negativeEstimatedCost,
        int costStatusMismatches) {

    /**
     * 运行时关闭时的空结果。
     *
     * @return 未执行的结果
     */
    public static ReconciliationResult skipped() {
        return new ReconciliationResult(false, 0, 0, 0, 0, 0);
    }

    /**
     * @return 是否存在需要人工介入的异常
     */
    public boolean hasAnomaly() {
        return quotaOverflowUsers > 0 || attributionMismatches > 0 || costStatusMismatches > 0;
    }
}
