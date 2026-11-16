package com.example.agent.pcbuild.web.dto;

import com.example.agent.pcbuild.domain.CompatibilityReport;
import com.example.agent.pcbuild.domain.CompatibilityStatus;
import java.util.List;

/**
 * 部分兼容性校验响应。
 *
 * <p>只包含依赖组件全部已选的规则，因此 {@code checks} 可能少于九条；
 * 没有任何规则可执行时 {@code overallStatus} 为 {@code UNKNOWN}。
 * 状态枚举与 {@code /validate} 一致（{@code PASS} / {@code WARNING} / {@code FAIL} / {@code UNKNOWN}），
 * {@code WARNING} 表示可用但缺少冗余，不代表通过。</p>
 *
 * @param overallStatus 已执行规则的最严重状态
 * @param checks        已执行规则的结论
 */
public record PartialValidateResponse(
        CompatibilityStatus overallStatus,
        List<PartialCompatibilityCheckResponse> checks) {

    /**
     * @param report 部分兼容性报告
     * @return 响应
     */
    public static PartialValidateResponse from(CompatibilityReport report) {
        return new PartialValidateResponse(
                report.overallStatus(),
                report.checks().stream().map(PartialCompatibilityCheckResponse::from).toList());
    }
}
