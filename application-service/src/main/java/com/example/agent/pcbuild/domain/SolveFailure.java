package com.example.agent.pcbuild.domain;

import java.util.List;
import java.util.Map;

/**
 * 结构化无解说明。
 *
 * @param reason                   原因分类
 * @param message                  面向调用方的说明
 * @param missingCategories        缺失候选的类别
 * @param candidateCounts          各类别候选数量
 * @param minimumRequiredBudgetFen 通过兼容校验的最低总价，单位分；仅预算不足时有值
 * @param evaluatedCombinationCount 实际评估的完整组合数
 */
public record SolveFailure(
        SolveFailureReason reason,
        String message,
        List<String> missingCategories,
        Map<String, Integer> candidateCounts,
        Long minimumRequiredBudgetFen,
        int evaluatedCombinationCount) {

    public SolveFailure {
        missingCategories = missingCategories == null ? List.of() : List.copyOf(missingCategories);
        candidateCounts = candidateCounts == null ? Map.of() : Map.copyOf(candidateCounts);
    }
}
