package com.example.agent.pcbuild.web.dto;

import com.example.agent.pcbuild.domain.BuildRequirements;
import com.example.agent.pcbuild.domain.BuildScenario;
import com.example.agent.pcbuild.domain.PcBuildErrorCode;
import com.example.agent.pcbuild.domain.Preference;
import com.example.agent.pcbuild.domain.RenderMode;
import com.example.agent.pcbuild.domain.WorkloadProfile;
import com.example.agent.shared.error.BusinessException;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;

/**
 * 求解请求。
 *
 * @param budgetMaxFen          预算上限，单位人民币分；为空表示无硬预算
 * @param budgetMinFen          预算下限，单位人民币分；为空表示用户只给了上限
 * @param minCpuPriceFen        CPU 价格下限，单位人民币分；质量评审带约束重解时使用
 * @param maxGpuPriceFen        GPU 价格上限，单位人民币分；质量评审带约束重解时使用
 * @param scenario              场景，默认 {@code BALANCED}
 * @param minMemoryGb           最低内存容量
 * @param minStorageGb          最低存储容量
 * @param requireVerifiedOffers 是否只接受人工核验价
 * @param renderMode            渲染取向，可空；为空时按 {@code BOTH} 处理
 * @param preference            选型偏好，可空；取值 {@code PERFORMANCE} 或 {@code VALUE}，忽略大小写
 */
public record SolveRequest(
        @Min(value = 0, message = "预算不能为负")
        Long budgetMaxFen,

        @Min(value = 0, message = "预算下限不能为负")
        Long budgetMinFen,

        @Min(value = 0, message = "CPU 价格下限不能为负")
        Long minCpuPriceFen,

        @Min(value = 0, message = "GPU 价格上限不能为负")
        Long maxGpuPriceFen,

        @Pattern(regexp = "(?i)GAMING|VIDEO_EDITING|CREATIVE|PROGRAMMING|WORKSTATION|OFFICE|MEDIA"
                + "|GENERAL|GENERAL_USE|BALANCED|RENDERING|AI_INFERENCE",
                message = "场景仅支持 GAMING/VIDEO_EDITING/CREATIVE/PROGRAMMING/WORKSTATION/OFFICE"
                        + "/MEDIA/GENERAL/GENERAL_USE/BALANCED/RENDERING/AI_INFERENCE")
        String scenario,

        @Min(value = 1, message = "内存容量至少 1GB")
        @Max(value = 512, message = "内存容量过大")
        Integer minMemoryGb,

        @Min(value = 1, message = "存储容量至少 1GB")
        @Max(value = 8192, message = "存储容量过大")
        Integer minStorageGb,

        Boolean requireVerifiedOffers,

        @Pattern(regexp = "(?i)CPU|GPU|BOTH", message = "渲染模式仅支持 CPU/GPU/BOTH")
        String renderMode,

        String preference) {

    /** 场景非法时面向调用方的统一提示。 */
    private static final String SCENARIO_MESSAGE =
            "场景仅支持 GAMING/VIDEO_EDITING/CREATIVE/PROGRAMMING/WORKSTATION/OFFICE"
                    + "/MEDIA/GENERAL/GENERAL_USE/BALANCED/RENDERING/AI_INFERENCE";

    /** 预算区间非法时面向调用方的统一提示。 */
    private static final String BUDGET_RANGE_MESSAGE = "预算下限不能大于预算上限";

    /** 渲染模式非法时面向调用方的统一提示。 */
    private static final String RENDER_MODE_MESSAGE = "渲染模式仅支持 CPU/GPU/BOTH";

    /** 选型偏好非法时面向调用方的统一提示。 */
    private static final String PREFERENCE_MESSAGE = "选型偏好仅支持 PERFORMANCE/VALUE";

    /**
     * 转换为领域需求。
     *
     * @return 领域需求
     * @throws BusinessException 场景、渲染模式、选型偏好无法识别或预算区间倒置时 400 {@code 40304}
     */
    public BuildRequirements toRequirements() {
        // 区间倒置属于用户输入错误，必须在契约层转成 400，不能让构造器抛出未捕获异常。
        if (budgetMinFen != null && budgetMaxFen != null && budgetMinFen > budgetMaxFen) {
            throw new BusinessException(PcBuildErrorCode.REQUIREMENT_INVALID, BUDGET_RANGE_MESSAGE);
        }
        BuildScenario parsedScenario = BuildScenario.parse(scenario);
        if (scenario != null && !scenario.isBlank() && parsedScenario == null) {
            throw new BusinessException(PcBuildErrorCode.REQUIREMENT_INVALID, SCENARIO_MESSAGE);
        }
        RenderMode parsedRenderMode = RenderMode.parse(renderMode);
        if (renderMode != null && !renderMode.isBlank() && parsedRenderMode == null) {
            throw new BusinessException(PcBuildErrorCode.REQUIREMENT_INVALID, RENDER_MODE_MESSAGE);
        }
        Preference parsedPreference = Preference.parse(preference);
        if (preference != null && !preference.isBlank() && parsedPreference == null) {
            throw new BusinessException(PcBuildErrorCode.REQUIREMENT_INVALID, PREFERENCE_MESSAGE);
        }
        // 画像优先按原始文本解析；旧别名（GENERAL_USE 等）解析不到时交给构造器按场景推导。
        WorkloadProfile workloadProfile = WorkloadProfile.parse(scenario);
        return new BuildRequirements(
                budgetMaxFen,
                budgetMinFen,
                minCpuPriceFen,
                maxGpuPriceFen,
                parsedScenario == null ? BuildRequirements.DEFAULT_SCENARIO : parsedScenario,
                minMemoryGb,
                minStorageGb,
                Boolean.TRUE.equals(requireVerifiedOffers),
                workloadProfile,
                parsedRenderMode,
                null,
                parsedPreference);
    }
}
