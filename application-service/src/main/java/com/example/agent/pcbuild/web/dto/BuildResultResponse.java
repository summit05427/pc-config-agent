package com.example.agent.pcbuild.web.dto;

import com.example.agent.pcbuild.domain.BudgetStatus;
import com.example.agent.pcbuild.domain.BuildResult;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * 已落库方案响应。
 *
 * <p>{@code totalPriceFen}/{@code budgetMaxFen}/{@code priceFen} 单位均为人民币分。</p>
 */
public record BuildResultResponse(
        UUID buildId,
        RequirementsResponse requirements,
        List<BuildComponentResponse> components,
        long totalPriceFen,
        Long budgetMaxFen,
        BudgetStatus budgetStatus,
        CompatibilityReportResponse compatibilityReport,
        String solverVersion,
        String compatibilityRuleVersion,
        String catalogVersion,
        String offerDataStatus,
        long verifiedOfferCount,
        long demoOfferCount,
        Instant createdAt) {

    /**
     * @param result 领域结果
     * @return 响应
     */
    public static BuildResultResponse from(BuildResult result) {
        return new BuildResultResponse(
                result.buildId(),
                RequirementsResponse.from(result.requirements()),
                result.components().stream().map(BuildComponentResponse::from).toList(),
                result.totalPriceFen(),
                result.budgetMaxFen(),
                result.budgetStatus(),
                CompatibilityReportResponse.from(result.compatibilityReport()),
                result.solverVersion(),
                result.compatibilityRuleVersion(),
                result.catalogVersion(),
                result.offerDataStatus(),
                result.verifiedOfferCount(),
                result.demoOfferCount(),
                result.createdAt());
    }
}
