package com.example.agent.feedback.web.dto;

/**
 * 单个原因的数量。
 *
 * @param reasonCode 原因枚举名
 * @param label      原因的中文说明，便于管理端直接展示
 * @param total      数量
 */
public record FeedbackReasonCount(String reasonCode, String label, long total) {
}
