package com.example.agent.pcbuild.domain;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * 已落库的方案结果。
 *
 * @param buildId                  快照标识
 * @param userId                   所属用户公开 ID
 * @param requirements             原始需求
 * @param components               八个硬件条目，顺序固定
 * @param totalPriceFen            总价，单位分
 * @param budgetMaxFen             预算上限，可为 {@code null}
 * @param budgetStatus             预算状态
 * @param compatibilityReport      兼容性报告
 * @param solverVersion            求解器版本
 * @param compatibilityRuleVersion 兼容规则版本
 * @param catalogVersion           硬件目录版本
 * @param offerDataStatus          报价数据状态
 * @param createdAt                创建时间
 */
public record BuildResult(
        UUID buildId,
        UUID userId,
        BuildRequirements requirements,
        List<BuildComponent> components,
        long totalPriceFen,
        Long budgetMaxFen,
        BudgetStatus budgetStatus,
        CompatibilityReport compatibilityReport,
        String solverVersion,
        String compatibilityRuleVersion,
        String catalogVersion,
        String offerDataStatus,
        Instant createdAt) {

    public BuildResult {
        components = components == null ? List.of() : List.copyOf(components);
    }

    /**
     * @return 人工核验报价的数量
     */
    public long verifiedOfferCount() {
        return components.stream()
                .filter(component -> component.offer() != null && component.offer().isVerifiedPrice())
                .count();
    }

    /**
     * @return 演示报价的数量
     */
    public long demoOfferCount() {
        return components.stream()
                .filter(component -> component.offer() != null && !component.offer().isVerifiedPrice())
                .count();
    }

    /**
     * 从草稿组装结果。
     *
     * @param userId    所属用户
     * @param buildId   快照标识
     * @param draft     求解草稿
     * @param createdAt 创建时间
     * @return 结果
     */
    public static BuildResult fromDraft(UUID userId, UUID buildId, BuildDraft draft, Instant createdAt) {
        List<BuildComponent> components = new ArrayList<>();
        for (HardwareCategory category : HardwareCategory.REQUIRED_CATEGORIES) {
            Hardware hardware = draft.selection().get(category);
            components.add(new BuildComponent(
                    hardware,
                    draft.offers().get(category),
                    draft.benchmarks().get(category),
                    hardware.specSummary()));
        }
        BudgetStatus budgetStatus = draft.requirements().hasBudget()
                ? BudgetStatus.WITHIN_BUDGET
                : BudgetStatus.NO_BUDGET;
        return new BuildResult(
                buildId,
                userId,
                draft.requirements(),
                components,
                draft.totalPriceFen(),
                draft.requirements().budgetMaxFen(),
                budgetStatus,
                draft.compatibilityReport(),
                BuildSolverVersion.SOLVER_VERSION,
                CompatibilityReport.RULE_VERSION,
                draft.catalogVersion(),
                draft.offerDataStatus(),
                createdAt);
    }
}
