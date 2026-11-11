package com.example.agent.feedback.domain;

import com.example.agent.shared.error.BusinessException;
import java.util.Locale;

/**
 * 踩的原因分类。
 *
 * <p>枚举值直接落库，管理端与导出按本枚举翻译成中文；新增取值必须同步管理端筛选白名单
 * （{@code AdminFeedbackQuery#reasonCode} 的正则），否则筛选会被参数校验拒绝。</p>
 */
public enum FeedbackReason {

    INACCURATE("信息不准确"),
    OFF_TOPIC("答非所问"),
    INCOMPLETE("回答不完整"),
    FORMAT("格式混乱"),
    UNSAFE("内容不当"),
    OTHER("其他");

    private final String label;

    FeedbackReason(String label) {
        this.label = label;
    }

    /**
     * 中文说明，用于管理端展示与 CSV 导出。
     *
     * @return 中文标签
     */
    public String label() {
        return label;
    }

    /**
     * 解析可选的踩原因。
     *
     * @param raw 原始取值，{@code null} 或空白表示不填
     * @return 对应枚举或 {@code null}
     * @throws BusinessException 取值不在白名单内时抛 {@link FeedbackErrorCode#REASON_INVALID}
     */
    public static FeedbackReason fromNullable(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        try {
            return valueOf(raw.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException exception) {
            throw new BusinessException(FeedbackErrorCode.REASON_INVALID);
        }
    }
}
