package com.example.agent.pcbuild.web.dto;

import com.example.agent.pcbuild.domain.SolveFailure;
import java.util.List;
import java.util.Map;

/**
 * 求解响应。
 *
 * <p>{@code solved=false} 时 {@code failure} 必填，{@code build} 为空；
 * 调用方不得在无解时自行放宽预算。</p>
 */
public record SolveResponse(boolean solved, BuildResultResponse build, Failure failure) {

    /**
     * 结构化无解说明。
     *
     * @param reason                   原因分类
     * @param message                  说明
     * @param missingCategories        缺失候选的类别
     * @param candidateCounts          各类别候选数量
     * @param minimumRequiredBudgetFen 最低可行总价，单位分
     * @param evaluatedCombinationCount 已评估组合数
     */
    public record Failure(
            String reason,
            String message,
            List<String> missingCategories,
            Map<String, Integer> candidateCounts,
            Long minimumRequiredBudgetFen,
            int evaluatedCombinationCount) {

        /**
         * @param failure 领域失败
         * @return 响应
         */
        public static Failure from(SolveFailure failure) {
            return new Failure(
                    failure.reason().name(),
                    failure.message(),
                    failure.missingCategories(),
                    failure.candidateCounts(),
                    failure.minimumRequiredBudgetFen(),
                    failure.evaluatedCombinationCount());
        }
    }

    /**
     * @param build 成功方案
     * @return 响应
     */
    public static SolveResponse solved(BuildResultResponse build) {
        return new SolveResponse(true, build, null);
    }

    /**
     * @param failure 失败原因
     * @return 响应
     */
    public static SolveResponse failed(Failure failure) {
        return new SolveResponse(false, null, failure);
    }
}
