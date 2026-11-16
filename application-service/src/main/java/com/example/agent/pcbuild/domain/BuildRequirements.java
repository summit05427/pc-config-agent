package com.example.agent.pcbuild.domain;

/**
 * 求解需求。
 *
 * @param budgetMaxFen           预算上限，单位分；{@code null} 表示无硬预算
 * @param budgetMinFen           预算下限，单位分；{@code null} 表示用户只给了上限
 * @param minCpuPriceFen         CPU 价格下限，单位分；来自质量评审的带约束重解，{@code null} 表示不限制
 * @param maxGpuPriceFen         GPU 价格上限，单位分；来自质量评审的带约束重解，{@code null} 表示不限制
 * @param scenario               场景，决定性能权重；调用方显式给出时原样保留（如 OFFICE 的 85/15）
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
        Long budgetMinFen,
        Long minCpuPriceFen,
        Long maxGpuPriceFen,
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
        if (budgetMinFen != null && budgetMinFen < 0) {
            throw new IllegalArgumentException("budgetMinFen must not be negative");
        }
        if (budgetMinFen != null && budgetMaxFen != null && budgetMinFen > budgetMaxFen) {
            throw new IllegalArgumentException("budgetMinFen must not exceed budgetMaxFen");
        }
        if (minCpuPriceFen != null && minCpuPriceFen < 0) {
            throw new IllegalArgumentException("minCpuPriceFen must not be negative");
        }
        if (maxGpuPriceFen != null && maxGpuPriceFen < 0) {
            throw new IllegalArgumentException("maxGpuPriceFen must not be negative");
        }
        if (renderMode == null) {
            renderMode = RenderMode.BOTH;
        }
        if (scoringVersion == null) {
            scoringVersion = ScoringPolicyVersion.SCORING_VERSION;
        }
        // 场景与画像只补默认值、不互相覆盖：画像能表达的场景由画像推导，
        // 画像表达不了的旧场景（如 OFFICE）必须保留调用方给出的权重，否则 OFFICE 会被折叠成 BALANCED。
        if (scenario == null) {
            scenario = workloadProfile == null
                    ? DEFAULT_SCENARIO
                    : workloadProfile.scenarioFor(renderMode);
        }
        if (workloadProfile == null) {
            workloadProfile = profileOf(scenario);
        }
        // 渲染画像的权重取决于渲染介质（CPU 渲染偏多核、GPU 渲染偏显卡），必须由画像重算；
        // 其余画像表达不了的场景（OFFICE / MEDIA 等）保留调用方传入的权重。
        if (workloadProfile == WorkloadProfile.RENDERING) {
            scenario = workloadProfile.scenarioFor(renderMode);
        }
    }

    /**
     * 兼容旧调用的九参构造：不含预算下限与质量约束。
     *
     * @param budgetMaxFen          预算上限，单位分
     * @param scenario              场景
     * @param minMemoryGb           最低内存容量
     * @param minStorageGb          最低存储容量
     * @param requireVerifiedOffers 是否只接受人工核验报价
     * @param workloadProfile       工作负载画像
     * @param renderMode            渲染取向
     * @param scoringVersion        评分策略版本
     * @param preference            选型偏好
     */
    public BuildRequirements(
            Long budgetMaxFen,
            BuildScenario scenario,
            Integer minMemoryGb,
            Integer minStorageGb,
            boolean requireVerifiedOffers,
            WorkloadProfile workloadProfile,
            RenderMode renderMode,
            String scoringVersion,
            Preference preference) {
        this(budgetMaxFen, null, null, null, scenario, minMemoryGb, minStorageGb,
                requireVerifiedOffers, workloadProfile, renderMode, scoringVersion, preference);
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
        this(budgetMaxFen, null, null, null, scenario, minMemoryGb, minStorageGb,
                requireVerifiedOffers, workloadProfile, renderMode, scoringVersion, null);
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
        this(budgetMaxFen, null, null, null, scenario, minMemoryGb, minStorageGb,
                requireVerifiedOffers, null, null, null, null);
    }

    /**
     * @return 是否存在硬预算
     */
    public boolean hasBudget() {
        return budgetMaxFen != null;
    }

    /**
     * 去掉预算上下限的副本，用于计算「最低可行总价」的探针搜索。
     *
     * <p>质量约束（CPU 价格下限 / GPU 价格上限）属于需求本身，探针必须沿用；
     * 只有预算上下限需要清空。</p>
     *
     * @return 预算为 {@code null}、其余条件不变的需求
     */
    public BuildRequirements withoutBudget() {
        return new BuildRequirements(null, null, minCpuPriceFen, maxGpuPriceFen, scenario,
                minMemoryGb, minStorageGb, requireVerifiedOffers, workloadProfile, renderMode,
                scoringVersion, preference);
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
            case MEDIA -> WorkloadProfile.MEDIA;
            case AI_INFERENCE -> WorkloadProfile.AI_INFERENCE;
        };
    }
}
