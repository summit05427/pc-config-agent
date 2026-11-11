package com.example.agent.pcbuild.web.dto;

import com.example.agent.pcbuild.domain.BuildRequirements;
import com.example.agent.pcbuild.domain.BuildScenario;
import com.example.agent.pcbuild.domain.Preference;
import com.example.agent.pcbuild.domain.RenderMode;
import com.example.agent.pcbuild.domain.WorkloadProfile;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * 求解需求响应/快照。
 *
 * <p>快照里必须保留画像、渲染取向、评分版本与选型偏好，否则历史结果无法解释分数差异。</p>
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record RequirementsResponse(
        Long budgetMaxFen,
        BuildScenario scenario,
        Integer minMemoryGb,
        Integer minStorageGb,
        boolean requireVerifiedOffers,
        WorkloadProfile workloadProfile,
        RenderMode renderMode,
        String scoringVersion,
        Preference preference) {

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
                requirements.requireVerifiedOffers(),
                requirements.workloadProfile(),
                requirements.renderMode(),
                requirements.scoringVersion(),
                requirements.preference());
    }

    /**
     * 从快照还原领域需求。
     *
     * @return 领域需求
     */
    public BuildRequirements toRequirements() {
        return new BuildRequirements(
                budgetMaxFen,
                scenario,
                minMemoryGb,
                minStorageGb,
                requireVerifiedOffers,
                workloadProfile,
                renderMode,
                scoringVersion,
                preference);
    }
}
