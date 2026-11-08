package com.example.agent.pcbuild.domain;

/**
 * 求解需求。
 *
 * @param budgetMaxFen           预算上限，单位分；{@code null} 表示无硬预算
 * @param scenario               场景，决定性能权重
 * @param minMemoryGb            最低内存容量，可空
 * @param minStorageGb           最低存储容量，可空
 * @param requireVerifiedOffers  是否只接受人工核验报价
 */
public record BuildRequirements(
        Long budgetMaxFen,
        BuildScenario scenario,
        Integer minMemoryGb,
        Integer minStorageGb,
        boolean requireVerifiedOffers) {

    public static final BuildScenario DEFAULT_SCENARIO = BuildScenario.BALANCED;

    public BuildRequirements {
        if (scenario == null) {
            scenario = DEFAULT_SCENARIO;
        }
        if (budgetMaxFen != null && budgetMaxFen < 0) {
            throw new IllegalArgumentException("budgetMaxFen must not be negative");
        }
    }

    /**
     * @return 是否存在硬预算
     */
    public boolean hasBudget() {
        return budgetMaxFen != null;
    }
}
