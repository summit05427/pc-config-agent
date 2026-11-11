package com.example.agent.feedback.infrastructure;

/**
 * 按原因聚合的计数行。
 *
 * @param reasonCode 原因枚举名
 * @param total      数量
 */
public record FeedbackReasonCountRow(String reasonCode, long total) {
}
