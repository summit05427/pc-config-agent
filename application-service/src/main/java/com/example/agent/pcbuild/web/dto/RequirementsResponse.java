package com.example.agent.pcbuild.web.dto;

import com.example.agent.pcbuild.domain.BuildRequirements;
import com.example.agent.pcbuild.domain.BuildScenario;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * 求解需求响应/快照。
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record RequirementsResponse(
        Long budgetMaxFen,
        BuildScenario scenario,
        Integer minMemoryGb,
        Integer minStorageGb,
        boolean requireVerifiedOffers) {

    /**
     * @param requirements 领域需求
     * @return 响应
     */
    public static RequirementsResponse from(BuildRequirements requirements) {
        return new RequirementsResponse(
                requirements.budgetMaxFen(),
                requirements.scenario(),
                requirements.minMemoryGb(),
                requirements.minStorageGb(),
                requirements.requireVerifiedOffers());
    }
}
