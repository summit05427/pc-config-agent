package com.example.agent.pcbuild.domain;

/**
 * 兼容性规则缺失信息的严重程度。
 *
 * <p>只描述「信息缺失」的影响，不替代 {@link CompatibilityStatus} 的
 * {@code PASS}/{@code WARNING}/{@code FAIL}/{@code UNKNOWN} 结论：
 * {@code BLOCKING} 表示该规则无法确认时不得给出推荐，{@code ADVISORY} 表示仅提示。</p>
 */
public enum RiskLevel {

    /** 信息缺失会阻断推荐。 */
    BLOCKING,

    /** 信息缺失只做提示，不阻断推荐。 */
    ADVISORY
}
