package com.example.agent.identity.web.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/**
 * 用户偏好更新请求，全量提交。
 *
 * <p>枚举字段刻意声明为 {@code String} + {@code @Pattern} 而不是 Java 枚举：
 * 非法取值会走 Bean Validation，返回 400 {@code 10001} 并附带字段级 {@code details}；
 * 若直接用枚举，Jackson 反序列化失败会退化成 {@code 10004}，前端拿不到具体字段。</p>
 *
 * <p>构造时统一去首尾空白，{@code instructions} 的空白值转 {@code null}，
 * 与资料接口保持同一套归一化语义。</p>
 *
 * @param instructions  自定义指令，可空，最长 1000
 * @param replyLanguage 回复语言，必填，只能是 {@code auto} / {@code zh-CN} / {@code en-US}
 * @param responseStyle 回复风格，必填，只能是 {@code concise} / {@code balanced} / {@code detailed}
 * @param useHistory    是否使用历史上下文，必填
 */
public record UserPreferenceUpdateRequest(
        @Size(max = 1000, message = "自定义指令不能超过 1000 个字符")
        String instructions,

        @NotBlank(message = "回复语言不能为空")
        @Pattern(regexp = "auto|zh-CN|en-US", message = "回复语言只能是 auto、zh-CN 或 en-US")
        String replyLanguage,

        @NotBlank(message = "回复风格不能为空")
        @Pattern(regexp = "concise|balanced|detailed", message = "回复风格只能是 concise、balanced 或 detailed")
        String responseStyle,

        @NotNull(message = "是否使用历史上下文不能为空")
        Boolean useHistory) {

    public UserPreferenceUpdateRequest {
        instructions = trimToNull(instructions);
        replyLanguage = trimToNull(replyLanguage);
        responseStyle = trimToNull(responseStyle);
    }

    private static String trimToNull(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
