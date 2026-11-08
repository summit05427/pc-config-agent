package com.example.agent.model.web.dto;

import jakarta.validation.constraints.NotNull;

/**
 * 管理端启用/停用 Provider 的请求体。
 *
 * @param enabled 目标状态；必须显式传值
 */
public record AdminProviderStatusUpdateRequest(
        @NotNull(message = "enabled 不能为空") Boolean enabled) {
}
