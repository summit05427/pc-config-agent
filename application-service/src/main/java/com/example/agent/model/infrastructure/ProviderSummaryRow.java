package com.example.agent.model.infrastructure;

/**
 * Provider 目录聚合行，用于 BYOK 供应商选择器。
 *
 * @param code            Provider 代码
 * @param displayName     展示名
 * @param protocol        通信协议
 * @param defaultBaseUrl  数据库中的默认地址，可为空
 * @param modelCount      该 Provider 下启用的模型数量
 */
public record ProviderSummaryRow(
        String code,
        String displayName,
        String protocol,
        String defaultBaseUrl,
        long modelCount) {
}
