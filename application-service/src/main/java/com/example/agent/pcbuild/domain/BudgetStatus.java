package com.example.agent.pcbuild.domain;

/**
 * 预算状态。
 */
public enum BudgetStatus {

    /** 有预算且总价未超。 */
    WITHIN_BUDGET,

    /** 未提供预算，按性能/价格平衡策略选择。 */
    NO_BUDGET
}
