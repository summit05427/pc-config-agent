package com.example.agent.model.domain;

/**
 * 面向 BYOK 供应商选择器的 Provider 摘要。
 *
 * @param code           Provider 代码
 * @param displayName    展示名
 * @param protocol       通信协议
 * @param defaultBaseUrl 目录中的默认地址，可为空；实际默认地址由网关决定
 * @param modelCount     目录中的模型数量
 */
public record ProviderSummary(
        String code,
        String displayName,
        String protocol,
        String defaultBaseUrl,
        long modelCount) {
}
