package com.example.agent.feedback.domain;

import com.example.agent.shared.error.BusinessException;
import java.util.Locale;

/**
 * 消息评分。
 *
 * <p>只保留赞与踩两种取值：中间档会让统计口径失去意义，细分诉求交给 {@link FeedbackReason}。</p>
 */
public enum FeedbackRating {

    UP,
    DOWN;

    /**
     * 解析请求中的评分字符串。
     *
     * @param raw 原始取值，允许 {@code null}
     * @return 对应枚举
     * @throws BusinessException 取值为空或不在白名单内时抛 {@link FeedbackErrorCode#RATING_INVALID}
     */
    public static FeedbackRating from(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new BusinessException(FeedbackErrorCode.RATING_INVALID);
        }
        try {
            return valueOf(raw.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException exception) {
            throw new BusinessException(FeedbackErrorCode.RATING_INVALID);
        }
    }
}
