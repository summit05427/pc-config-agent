package com.example.agent.model.infrastructure;

/**
 * 管理端 Provider 目录行，含模型数量统计。
 *
 * @param code              Provider 代码
 * @param displayName       展示名
 * @param protocol          通信协议
 * @param defaultBaseUrl    默认接入地址，可为空
 * @param enabled           Provider 是否启用
 * @param modelCount        该 Provider 下模型总数
 * @param enabledModelCount 该 Provider 下已启用模型数
 */
public record AdminProviderRow(
        String code,
        String displayName,
        String protocol,
        String defaultBaseUrl,
        Boolean enabled,
        Long modelCount,
        Long enabledModelCount) {
}
