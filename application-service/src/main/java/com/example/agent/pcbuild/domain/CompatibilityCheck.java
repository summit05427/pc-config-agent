package com.example.agent.pcbuild.domain;

import java.util.List;

/**
 * 单条兼容性规则结论。
 *
 * @param ruleId     规则稳定标识
 * @param ruleName   规则名称
 * @param status     结论
 * @param riskLevel  信息缺失的严重程度，不替代 {@code status}
 * @param message    面向调用方的说明；{@code UNKNOWN} 必须写明缺失字段
 * @param hardwareIds 参与判断的硬件标识
 */
public record CompatibilityCheck(
        String ruleId,
        String ruleName,
        CompatibilityStatus status,
        RiskLevel riskLevel,
        String message,
        List<String> hardwareIds) {

    public CompatibilityCheck {
        hardwareIds = hardwareIds == null ? List.of() : List.copyOf(hardwareIds);
    }
}
