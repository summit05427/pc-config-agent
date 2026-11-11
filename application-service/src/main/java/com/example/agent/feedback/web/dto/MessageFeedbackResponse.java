package com.example.agent.feedback.web.dto;

/**
 * 用户侧反馈视图，用于提交后的回显与刷新后的高亮恢复。
 *
 * @param messageId  稳定消息标识
 * @param rating     评分
 * @param reasonCode 踩的原因，未填或点赞时为 {@code null}
 */
public record MessageFeedbackResponse(String messageId, String rating, String reasonCode) {
}
