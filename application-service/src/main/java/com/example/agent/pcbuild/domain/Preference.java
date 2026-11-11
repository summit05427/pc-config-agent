package com.example.agent.pcbuild.domain;

import java.util.Locale;

/**
 * 用户选型偏好。
 *
 * <p>{@code PERFORMANCE} 表示预算内优先性能总分；{@code VALUE} 表示预算内优先性价比。
 * {@code null}（未传入）保持求解器原有行为：有预算时按性能总分，无预算时按性价比。</p>
 */
public enum Preference {

    PERFORMANCE,
    VALUE;

    /**
     * 解析外部传入的偏好名，忽略大小写。
     *
     * @param raw 原始文本，可为 {@code null}
     * @return 命中偏好；无法识别时为 {@code null}
     */
    public static Preference parse(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        return switch (raw.trim().toUpperCase(Locale.ROOT)) {
            case "PERFORMANCE" -> PERFORMANCE;
            case "VALUE" -> VALUE;
            default -> null;
        };
    }
}
