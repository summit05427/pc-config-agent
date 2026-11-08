package com.example.agent.pcbuild.web.dto;

import com.example.agent.pcbuild.domain.CompatibilityCheck;
import com.example.agent.pcbuild.domain.CompatibilityStatus;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.List;

/**
 * 单条兼容性结论响应。
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record CompatibilityCheckResponse(
        String ruleId,
        String ruleName,
        CompatibilityStatus status,
        String message,
        List<String> hardwareIds) {

    /**
     * @param check 领域结论
     * @return 响应
     */
    public static CompatibilityCheckResponse from(CompatibilityCheck check) {
        return new CompatibilityCheckResponse(
                check.ruleId(),
                check.ruleName(),
                check.status(),
                check.message(),
                check.hardwareIds());
    }
}
