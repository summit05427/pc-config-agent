package com.example.agent.pcbuild.web.dto;

import com.example.agent.pcbuild.domain.CompatibilityReport;
import com.example.agent.pcbuild.domain.CompatibilityStatus;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.List;

/**
 * 兼容性报告响应。
 *
 * <p>{@code overallStatus=UNKNOWN} 表示存在无法确认的规则，不能展示为通过。</p>
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record CompatibilityReportResponse(
        String ruleVersion,
        CompatibilityStatus overallStatus,
        boolean hasFailure,
        List<CompatibilityCheckResponse> checks) {

    /**
     * @param report 领域报告
     * @return 响应
     */
    public static CompatibilityReportResponse from(CompatibilityReport report) {
        return new CompatibilityReportResponse(
                report.ruleVersion(),
                report.overallStatus(),
                report.hasFailure(),
                report.checks().stream().map(CompatibilityCheckResponse::from).toList());
    }
}
