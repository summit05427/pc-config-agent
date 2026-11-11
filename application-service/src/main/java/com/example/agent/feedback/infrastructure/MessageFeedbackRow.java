package com.example.agent.feedback.infrastructure;

/**
 * 用户侧反馈行：只取恢复高亮所需的最小字段。
 *
 * @param messageId  稳定消息标识
 * @param rating     评分，{@code UP} 或 {@code DOWN}
 * @param reasonCode 踩的原因，点赞或未填时为 {@code null}
 */
public record MessageFeedbackRow(String messageId, String rating, String reasonCode) {
}
