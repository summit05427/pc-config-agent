package com.example.agent.pcbuild.domain;

/**
 * 求解结果：成功或结构化失败，二者互斥。
 *
 * @param build   成功方案；失败时为 {@code null}
 * @param failure 失败原因；成功时为 {@code null}
 */
public record SolveOutcome(BuildDraft build, SolveFailure failure) {

    public SolveOutcome {
        if ((build == null) == (failure == null)) {
            throw new IllegalArgumentException("exactly one of build or failure must be present");
        }
    }

    public static SolveOutcome solved(BuildDraft build) {
        return new SolveOutcome(build, null);
    }

    public static SolveOutcome failed(SolveFailure failure) {
        return new SolveOutcome(null, failure);
    }

    public boolean isSolved() {
        return build != null;
    }
}
