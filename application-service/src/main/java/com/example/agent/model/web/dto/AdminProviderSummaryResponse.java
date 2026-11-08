package com.example.agent.model.web.dto;

/**
 * 管理端 Provider 摘要。
 *
 * @param code              Provider 代码
 * @param displayName       展示名
 * @param protocol          通信协议
 * @param defaultBaseUrl    默认接入地址，可为空
 * @param enabled           Provider 是否启用
 * @param modelCount        模型总数
 * @param enabledModelCount 已启用模型数
 */
public record AdminProviderSummaryResponse(
        String code,
        String displayName,
        String protocol,
        String defaultBaseUrl,
        boolean enabled,
        long modelCount,
        long enabledModelCount) {
}
