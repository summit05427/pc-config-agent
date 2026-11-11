package com.example.agent.feedback.infrastructure;

import java.time.OffsetDateTime;

/**
 * 管理端反馈行：附带提交者登录名。
 *
 * @param userId     提交者公开 ID（JWT sub）
 * @param username   登录名，用户已删除时为 {@code null}
 * @param threadId   会话标识
 * @param messageId  稳定消息标识
 * @param rating     评分
 * @param reasonCode 踩的原因
 * @param comment    用户备注
 * @param createdAt  提交时间
 */
public record AdminFeedbackRow(
        String userId,
        String username,
        String threadId,
        String messageId,
        String rating,
        String reasonCode,
        String comment,
        OffsetDateTime createdAt) {
}
