package com.example.agent.pcbuild.domain;

/**
 * 求解器版本常量。
 *
 * <p>与 {@link CompatibilityReport#RULE_VERSION} 分开：求解策略变化（评分、剪枝、tie-break）
 * 递增求解器版本，兼容规则变化递增规则版本，快照据此判断历史结果是否可比较。</p>
 */
public final class BuildSolverVersion {

    /** 当前求解器版本。 */
    public static final String SOLVER_VERSION = "pc-solver-2.1.0";

    private BuildSolverVersion() {
    }
}
