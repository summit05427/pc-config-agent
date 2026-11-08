package com.example.agent.pcbuild.domain;

/**
 * 无解原因。
 *
 * <p>无解是正常业务结果，不是异常：调用方需要拿到结构化原因才能向用户解释，
 * 但任何情况下都不得放宽预算或忽略硬冲突。</p>
 */
public enum SolveFailureReason {

    /** 某类别没有任何可参与求解的候选（无有效报价或全部不合格）。 */
    NO_CANDIDATES,

    /** 候选存在，但八条规则中没有一组组合能通过。 */
    NO_COMPATIBLE_BUILD,

    /** 存在兼容组合，但全部超过预算。 */
    BUDGET_EXCEEDED
}
