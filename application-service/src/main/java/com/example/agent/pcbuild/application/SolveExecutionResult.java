package com.example.agent.pcbuild.application;

import com.example.agent.pcbuild.domain.BuildResult;
import com.example.agent.pcbuild.domain.SolveFailure;
import java.util.Objects;

/**
 * 求解执行结果：成功返回已落库方案，失败返回结构化原因。
 *
 * @param build   已落库方案；失败时为 {@code null}
 * @param failure 失败原因；成功时为 {@code null}
 */
public record SolveExecutionResult(BuildResult build, SolveFailure failure) {

    public SolveExecutionResult {
        if ((build == null) == (failure == null)) {
            throw new IllegalArgumentException("exactly one of build or failure must be present");
        }
    }

    /**
     * @param build 已落库方案
     * @return 成功结果
     */
    public static SolveExecutionResult solved(BuildResult build) {
        return new SolveExecutionResult(Objects.requireNonNull(build), null);
    }

    /**
     * @param failure 失败原因
     * @return 失败结果
     */
    public static SolveExecutionResult failed(SolveFailure failure) {
        return new SolveExecutionResult(null, Objects.requireNonNull(failure));
    }

    /**
     * @return 是否成功
     */
    public boolean isSolved() {
        return build != null;
    }
}
