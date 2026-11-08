package com.example.agent.model.web.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 轮换 Provider 凭证的请求。
 *
 * <p>Provider 代码不可变更，只能换密钥或调整接入地址；{@code baseUrl} 留空表示
 * 沿用原地址。</p>
 *
 * @param baseUrl 新接入地址，可为空
 * @param apiKey  新明文密钥，去空白后 8..512 字符
 */
public record ModelConnectionUpdateRequest(
        @Size(max = 255, message = "baseUrl 长度不能超过 255")
        String baseUrl,

        @NotBlank(message = "apiKey 不能为空")
        @Size(min = 8, max = 512, message = "apiKey 长度必须在 8..512 之间")
        String apiKey) {
}
