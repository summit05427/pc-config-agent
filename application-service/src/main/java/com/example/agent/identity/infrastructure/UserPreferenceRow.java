package com.example.agent.identity.infrastructure;

import java.time.Instant;
import lombok.Getter;
import lombok.Setter;

/**
 * {@code user_preferences} 表的行映射对象。
 *
 * <p>MyBatis 需要无参构造与 setter，因此不使用 record；
 * 枚举字符串到领域枚举的转换留在 {@link MyBatisUserPreferenceDirectory}。</p>
 */
@Getter
@Setter
public class UserPreferenceRow {

    private String instructions;
    private String replyLanguage;
    private String responseStyle;
    private Boolean useHistory;
    private Instant updatedAt;
}
