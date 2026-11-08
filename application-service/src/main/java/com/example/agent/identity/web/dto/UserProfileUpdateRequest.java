package com.example.agent.identity.web.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 个人资料更新请求。
 *
 * <p>校验在服务端完成：前端校验只用于即时反馈，不能作为边界。
 * 归一化在构造时统一完成，避免「校验看到原值、落库看到归值」两套语义：</p>
 * <ul>
 *   <li>三个字段统一去掉首尾空白；</li>
 *   <li>{@code email} / {@code bio} 的空白值转成 {@code null}（{@code email} 有唯一约束，多个空串会互相冲突）。</li>
 * </ul>
 *
 * @param displayName 展示名，去除首尾空白后 1..64，不可为空白
 * @param email       邮箱，可空，最长 255
 * @param bio         个人简介，可空，最长 500
 */
public record UserProfileUpdateRequest(
        @NotBlank(message = "展示名不能为空")
        @Size(max = 64, message = "展示名不能超过 64 个字符")
        String displayName,

        @Email(message = "邮箱格式不正确")
        @Size(max = 255, message = "邮箱不能超过 255 个字符")
        String email,

        @Size(max = 500, message = "个人简介不能超过 500 个字符")
        String bio) {

    /**
     * 构造时归一化：去首尾空白，空白值转 {@code null}。
     *
     * <p>Jackson 反序列化记录时走规范构造器，因此这一步在参数校验之前生效，
     * 使「纯空格邮箱」等同「未填写」而不是被判为格式错误。</p>
     */
    public UserProfileUpdateRequest {
        displayName = trimToNull(displayName);
        email = trimToNull(email);
        bio = trimToNull(bio);
    }

    private static String trimToNull(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
