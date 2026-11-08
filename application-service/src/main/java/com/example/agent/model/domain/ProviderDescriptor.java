package com.example.agent.model.domain;

/**
 * Provider 目录的只读描述，供连接服务判断是否受支持。
 *
 * <p>不使用 {@link ProviderSummary}：连接校验不需要模型数量，避免伪造无意义的计数。</p>
 *
 * @param code           Provider 代码
 * @param displayName    展示名
 * @param protocol       通信协议
 * @param defaultBaseUrl 默认接入地址，可为空
 */
public record ProviderDescriptor(
        String code,
        String displayName,
        String protocol,
        String defaultBaseUrl) {
}
