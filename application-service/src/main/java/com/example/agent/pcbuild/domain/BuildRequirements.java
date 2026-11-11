package com.example.agent.pcbuild.domain;

/**
 * 求解需求。
 *
 * @param budgetMaxFen           预算上限，单位分；{@code null} 表示无硬预算
 * @param scenario               场景，决定性能权重；与画像不一致时以画像重算
 * @param minMemoryGb            最低内存容量，可空
 * @param minStorageGb           最低存储容量，可空
 * @param requireVerifiedOffers  是否只接受人工核验报价
 * @param workloadProfile        工作负载画像，决定排序策略与评分细则
 * @param renderMode             渲染取向，{@code null} 视为 {@code BOTH}
 * @param scoringVersion         评分策略版本，{@code null} 取当前版本
 * @param preference             选型偏好；{@code null} 表示维持原有选优策略
 */
public record BuildRequirements(
        Long budgetMaxFen,
        BuildScenario scenario,
        Integer minMemoryGb,
        Integer minStorageGb,
        boolean requireVerifiedOffers,
        WorkloadProfile workloadProfile,
        RenderMode renderMode,
        String scoringVersion,
        Preference preference) {

    public static final BuildScenario DEFAULT_SCENARIO = BuildScenario.BALANCED;

    public BuildRequirements {
        if (budgetMaxFen != null && budgetMaxFen < 0) {
            throw new IllegalArgumentException("budgetMaxFen must not be negative");
        }
        if (scenario == null) {
            scenario = DEFAULT_SCENARIO;
        }
        if (renderMode == null) {
            renderMode = RenderMode.BOTH;
        }
        if (scoringVersion == null) {
            scoringVersion = ScoringPolicyVersion.SCORING_VERSION;
        }
        if (workloadProfile == null) {
            workloadProfile = profileOf(scenario);
        }
        // 场景权重只能由「画像 + 渲染取向」推导，避免调用方传入与画像矛盾的权重。
        BuildScenario derived = workloadProfile.scenarioFor(renderMode);
        if (scenario != derived) {
            scenario = derived;
        }
    }

    /**
     * 兼容旧调用的八参构造：偏好为 {@code null}，保持原有选优策略。
     *
     * @param budgetMaxFen          预算上限，单位分
     * @param scenario              场景
     * @param minMemoryGb           最低内存容量
     * @param minStorageGb          最低存储容量
     * @param requireVerifiedOffers 是否只接受人工核验报价
     * @param workloadProfile       工作负载画像
     * @param renderMode            渲染取向
     * @param scoringVersion        评分策略版本
     */
    public BuildRequirements(
            Long budgetMaxFen,
            BuildScenario scenario,
            Integer minMemoryGb,
            Integer minStorageGb,
            boolean requireVerifiedOffers,
            WorkloadProfile workloadProfile,
            RenderMode renderMode,
            String scoringVersion) {
        this(budgetMaxFen, scenario, minMemoryGb, minStorageGb, requireVerifiedOffers,
                workloadProfile, renderMode, scoringVersion, null);
    }

    /**
     * 兼容旧调用的五参构造：画像与渲染取向由场景推导。
     *
     * @param budgetMaxFen          预算上限，单位分
     * @param scenario              场景
     * @param minMemoryGb           最低内存容量
     * @param minStorageGb          最低存储容量
     * @param requireVerifiedOffers 是否只接受人工核验报价
     */
    public BuildRequirements(
            Long budgetMaxFen,
            BuildScenario scenario,
            Integer minMemoryGb,
            Integer minStorageGb,
            boolean requireVerifiedOffers) {
        this(budgetMaxFen, scenario, minMemoryGb, minStorageGb, requireVerifiedOffers,
                null, null, null, null);
    }

    /**
     * @return 是否存在硬预算
     */
    public boolean hasBudget() {
        return budgetMaxFen != null;
    }

    /**
     * 去掉预算上限的副本，用于计算「最低可行总价」的探针搜索。
     *
     * @return 预算为 {@code null}、其余条件不变的需求
     */
    public BuildRequirements withoutBudget() {
        return new BuildRequirements(null, scenario, minMemoryGb, minStorageGb,
                requireVerifiedOffers, workloadProfile, renderMode, scoringVersion, preference);
    }

    /**
     * @return 是否显式要求性价比优先
     */
    public boolean prefersValue() {
        return preference == Preference.VALUE;
    }

    /**
     * 由旧场景反推画像；旧场景包含 {@code OFFICE} 等画像中不存在的值，统一收敛到最接近的画像。
     */
    private static WorkloadProfile profileOf(BuildScenario scenario) {
        return switch (scenario) {
            case GAMING -> WorkloadProfile.GAMING;
            case CREATIVE -> WorkloadProfile.VIDEO_EDITING;
            case PROGRAMMING -> WorkloadProfile.PROGRAMMING;
            case WORKSTATION -> WorkloadProfile.RENDERING;
            case OFFICE, BALANCED -> WorkloadProfile.GENERAL;
            case AI_INFERENCE -> WorkloadProfile.AI_INFERENCE;
        };
    }
}
