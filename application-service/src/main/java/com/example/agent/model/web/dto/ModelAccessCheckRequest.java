package com.example.agent.model.web.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 模型可用性校验请求。
 *
 * @param modelKey 模型引用 {@code <provider>:<modelKey>}
 */
public record ModelAccessCheckRequest(
        @NotBlank(message = "modelKey 不能为空")
        @Size(max = 64, message = "modelKey 长度不能超过 64")
        String modelKey) {
}
