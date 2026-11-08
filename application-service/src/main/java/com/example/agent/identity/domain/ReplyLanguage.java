package com.example.agent.identity.domain;

import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import java.util.Arrays;

/**
 * 回复语言偏好。
 *
 * <p>{@code wireValue} 是前后端与数据库共用的取值，必须与
 * {@code user_preferences.reply_language} 的取值、前端表单选项保持一致。</p>
 */
public enum ReplyLanguage {

    AUTO("auto"),
    ZH_CN("zh-CN"),
    EN_US("en-US");

    private final String wireValue;

    ReplyLanguage(String wireValue) {
        this.wireValue = wireValue;
    }

    /**
     * 对外取值，用于 API 响应与数据库写入。
     *
     * @return 与前端约定的字符串值
     */
    public String wireValue() {
        return wireValue;
    }

    /**
     * 把请求或数据库中的取值转换成领域枚举。
     *
     * @param wireValue 对外取值的字符串
     * @return 对应的枚举
     * @throws BusinessException 取值不在白名单内时抛 {@link CommonErrorCode#PARAM_INVALID}
     */
    public static ReplyLanguage fromWireValue(String wireValue) {
        return Arrays.stream(values())
                .filter(language -> language.wireValue.equals(wireValue))
                .findFirst()
                .orElseThrow(() -> new BusinessException(CommonErrorCode.PARAM_INVALID, "回复语言取值不合法"));
    }
}
