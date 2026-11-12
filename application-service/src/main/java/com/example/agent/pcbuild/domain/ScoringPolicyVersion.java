package com.example.agent.pcbuild.domain;

/**
 * 评分策略版本常量。
 *
 * <p>与 {@link BuildSolverVersion#SOLVER_VERSION}、{@link CompatibilityReport#RULE_VERSION}
 * 互相独立：评分公式（权重、加成、量纲对齐）变化时只递增本版本，便于快照区分
 * 「同样的输入为什么分数不同」。设计依据见
 * {@code docs/adr/0027-pc-config-decisions.md} §4.2。</p>
 */
public final class ScoringPolicyVersion {

    /** 当前评分策略版本。 */
    public static final String SCORING_VERSION = "pc-scoring-1.0.0";

    private ScoringPolicyVersion() {
    }
}
