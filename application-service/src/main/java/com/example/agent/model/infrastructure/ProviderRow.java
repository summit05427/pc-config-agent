package com.example.agent.model.infrastructure;

/**
 * Provider 目录行。
 *
 * @param code           Provider 代码，如 {@code openai}
 * @param displayName    展示名
 * @param protocol       通信协议，首版固定 {@code openai-compatible}
 * @param defaultBaseUrl 默认接入地址，可为空
 */
public record ProviderRow(
        String code,
        String displayName,
        String protocol,
        String defaultBaseUrl) {
}
