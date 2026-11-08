package com.example.agent.model.web.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 创建 Provider 连接的请求。
 *
 * <p>{@code apiKey} 只在本次请求体中出现，服务端加密后立即丢弃；任何日志与响应
 * 都不得回显该字段。</p>
 *
 * @param providerCode Provider 代码，如 {@code openai}
 * @param baseUrl      自定义接入地址，可为空（由网关使用 Provider 官方默认地址）
 * @param apiKey       明文密钥，去空白后 8..512 字符
 */
public record ModelConnectionCreateRequest(
        @NotBlank(message = "providerCode 不能为空")
        @Size(max = 32, message = "providerCode 长度不能超过 32")
        String providerCode,

        @Size(max = 255, message = "baseUrl 长度不能超过 255")
        String baseUrl,

        @NotBlank(message = "apiKey 不能为空")
        @Size(min = 8, max = 512, message = "apiKey 长度必须在 8..512 之间")
        String apiKey) {
}
