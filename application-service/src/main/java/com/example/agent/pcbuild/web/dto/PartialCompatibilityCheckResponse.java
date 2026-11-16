package com.example.agent.pcbuild.web.dto;

import com.example.agent.pcbuild.domain.CompatibilityCheck;
import com.example.agent.pcbuild.domain.CompatibilityStatus;
import java.util.List;

/**
 * 部分兼容性校验中的单条规则结论。
 *
 * @param ruleId       规则稳定标识
 * @param status       结论；字段缺失时为 {@code UNKNOWN}，不得折算为 {@code PASS}
 * @param componentIds 参与判断的硬件标识
 * @param missingFields 导致 {@code UNKNOWN} 的缺失字段，格式 {@code 类别.字段}；
 *                      组件未选导致规则未执行时不会出现该规则
 */
public record PartialCompatibilityCheckResponse(
        String ruleId,
        CompatibilityStatus status,
        List<String> componentIds,
        List<String> missingFields) {

    /**
     * @param check 领域结论
     * @return 响应
     */
    public static PartialCompatibilityCheckResponse from(CompatibilityCheck check) {
        return new PartialCompatibilityCheckResponse(
                check.ruleId(),
                check.status(),
                check.hardwareIds(),
                check.missingFields());
    }
}
