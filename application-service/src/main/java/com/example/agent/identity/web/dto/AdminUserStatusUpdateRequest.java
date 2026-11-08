package com.example.agent.identity.web.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

/**
 * 管理端账号状态变更请求。
 *
 * @param status 目标状态，只允许 {@code ACTIVE} 或 {@code DISABLED}
 */
public record AdminUserStatusUpdateRequest(
        @NotBlank(message = "status 不能为空")
        @Pattern(regexp = "ACTIVE|DISABLED", message = "status 只能是 ACTIVE 或 DISABLED")
        String status) {
}
