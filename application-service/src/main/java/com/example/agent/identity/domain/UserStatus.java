package com.example.agent.identity.domain;

import java.util.Locale;

/**
 * 账号状态。
 *
 * <p>未知取值一律按 {@link #DISABLED} 处理：数据库里出现脏数据时宁可拒绝登录，
 * 也不要放行一个状态不明的账号。</p>
 */
public enum UserStatus {

    ACTIVE,
    DISABLED;

    /**
     * 把数据库中的字符串解析为枚举。
     *
     * @param value 数据库存储值，可为 {@code null}
     * @return 匹配的状态；无法识别时返回 {@link #DISABLED}
     */
    public static UserStatus from(String value) {
        if (value == null) {
            return DISABLED;
        }
        String normalized = value.trim().toUpperCase(Locale.ROOT);
        for (UserStatus status : values()) {
            if (status.name().equals(normalized)) {
                return status;
            }
        }
        return DISABLED;
    }

    public boolean isActive() {
        return this == ACTIVE;
    }
}
