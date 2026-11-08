package com.example.agent.pcbuild.web.dto;

import com.example.agent.pcbuild.domain.BuildRequirements;
import com.example.agent.pcbuild.domain.BuildScenario;
import com.example.agent.pcbuild.domain.PcBuildErrorCode;
import com.example.agent.shared.error.BusinessException;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;

/**
 * 求解请求。
 *
 * @param budgetMaxFen          预算上限，单位人民币分；为空表示无硬预算
 * @param scenario              场景，默认 {@code BALANCED}
 * @param minMemoryGb           最低内存容量
 * @param minStorageGb          最低存储容量
 * @param requireVerifiedOffers 是否只接受人工核验价
 */
public record SolveRequest(
        @Min(value = 0, message = "预算不能为负")
        Long budgetMaxFen,

        @Pattern(regexp = "(?i)GAMING|VIDEO_EDITING|CREATIVE|PROGRAMMING|WORKSTATION|OFFICE|GENERAL_USE|BALANCED",
                message = "场景仅支持 GAMING/VIDEO_EDITING/CREATIVE/PROGRAMMING/WORKSTATION/OFFICE/GENERAL_USE/BALANCED")
        String scenario,

        @Min(value = 1, message = "内存容量至少 1GB")
        @Max(value = 512, message = "内存容量过大")
        Integer minMemoryGb,

        @Min(value = 1, message = "存储容量至少 1GB")
        @Max(value = 8192, message = "存储容量过大")
        Integer minStorageGb,

        Boolean requireVerifiedOffers) {

    /**
     * 转换为领域需求。
     *
     * @return 领域需求
     * @throws BusinessException 场景无法识别时 400 {@code 40304}
     */
    public BuildRequirements toRequirements() {
        BuildScenario parsedScenario = BuildScenario.parse(scenario);
        if (scenario != null && !scenario.isBlank() && parsedScenario == null) {
            throw new BusinessException(PcBuildErrorCode.REQUIREMENT_INVALID,
                    "场景仅支持 GAMING/VIDEO_EDITING/CREATIVE/PROGRAMMING/WORKSTATION/OFFICE/GENERAL_USE/BALANCED");
        }
        return new BuildRequirements(
                budgetMaxFen,
                parsedScenario == null ? BuildRequirements.DEFAULT_SCENARIO : parsedScenario,
                minMemoryGb,
                minStorageGb,
                Boolean.TRUE.equals(requireVerifiedOffers));
    }
}
