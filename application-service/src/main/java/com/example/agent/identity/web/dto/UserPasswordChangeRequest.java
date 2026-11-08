package com.example.agent.identity.web.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 修改口令请求。
 *
 * <p>口令不做去空白处理：登录时也不会 trim，两侧必须看到完全一致的值，
 * 否则带首尾空白的口令会在改密后无法登录。</p>
 *
 * @param currentPassword 当前口令，用于确认操作者为账号本人
 * @param newPassword     新口令，长度 8..64，且不得与当前口令相同（由服务层比对）
 */
public record UserPasswordChangeRequest(
        @NotBlank(message = "当前口令不能为空")
        @Size(max = 128, message = "当前口令长度不能超过 128")
        String currentPassword,

        @NotBlank(message = "新口令不能为空")
        @Size(min = 8, max = 64, message = "新口令长度必须在 8 到 64 之间")
        String newPassword) {
}
