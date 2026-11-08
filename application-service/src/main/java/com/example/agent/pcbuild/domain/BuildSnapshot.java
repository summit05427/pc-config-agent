package com.example.agent.pcbuild.domain;

import java.time.Instant;
import java.util.UUID;

/**
 * 方案快照持久化载体。
 *
 * <p>JSON 字段以字符串形式在仓储层与数据库 {@code jsonb} 列之间传递，
 * 上层不感知数据库类型。表为 append-only：只新增快照，不更新、不删除。</p>
 *
 * @param buildId                  快照标识
 * @param userId                   所属用户公开 ID（JWT {@code sub}）
 * @param parentBuildId            父快照，可为 {@code null}
 * @param requirementsSnapshot     需求快照 JSON
 * @param components               硬件条目 JSON
 * @param totalPriceFen            总价，单位分
 * @param budgetMaxFen             预算上限，可为 {@code null}
 * @param compatibilityReport      兼容性报告 JSON
 * @param benchmarkSnapshot        跑分快照 JSON
 * @param offerSnapshot            报价快照 JSON
 * @param solverVersion            求解器版本
 * @param compatibilityRuleVersion 兼容规则版本
 * @param catalogVersion           目录版本
 * @param createdAt                创建时间
 */
public record BuildSnapshot(
        UUID buildId,
        UUID userId,
        UUID parentBuildId,
        String requirementsSnapshot,
        String components,
        long totalPriceFen,
        Long budgetMaxFen,
        String compatibilityReport,
        String benchmarkSnapshot,
        String offerSnapshot,
        String solverVersion,
        String compatibilityRuleVersion,
        String catalogVersion,
        Instant createdAt) {
}
