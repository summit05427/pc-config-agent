package com.example.agent.pcbuild.domain;

import java.util.List;

/**
 * 兼容性报告。
 *
 * @param ruleVersion   规则版本，随快照落库
 * @param overallStatus 八条规则中最严重的状态
 * @param checks        八条规则结论，顺序固定
 */
public record CompatibilityReport(
        String ruleVersion,
        CompatibilityStatus overallStatus,
        List<CompatibilityCheck> checks) {

    /** 当前规则版本；规则语义变化时必须递增。 */
    public static final String RULE_VERSION = "pc-compat-2.0.0";

    public CompatibilityReport {
        checks = checks == null ? List.of() : List.copyOf(checks);
    }

    /**
     * @return 是否存在硬冲突
     */
    public boolean hasFailure() {
        return checks.stream().anyMatch(check -> check.status() == CompatibilityStatus.FAIL);
    }

    /**
     * 汇总八条规则的状态；空列表视为 {@code UNKNOWN}，避免把「未校验」误报为通过。
     *
     * @param checks 规则结论
     * @return 最严重状态
     */
    public static CompatibilityStatus aggregate(List<CompatibilityCheck> checks) {
        if (checks == null || checks.isEmpty()) {
            return CompatibilityStatus.UNKNOWN;
        }
        CompatibilityStatus status = CompatibilityStatus.PASS;
        for (CompatibilityCheck check : checks) {
            status = CompatibilityStatus.worst(status, check.status());
        }
        return status;
    }
}
