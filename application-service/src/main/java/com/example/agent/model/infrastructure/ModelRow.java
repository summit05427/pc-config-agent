package com.example.agent.model.infrastructure;

/**
 * 模型目录行（{@code models} 联 {@code providers}）。
 *
 * <p>{@code capabilitiesJson} 保持原始 JSON 文本，由服务层解析，避免为单个字段引入自定义
 * TypeHandler。</p>
 *
 * @param providerCode     Provider 代码
 * @param modelKey         Provider 侧模型标识
 * @param displayName      展示名
 * @param contextWindow    上下文窗口，可空
 * @param capabilitiesJson 能力数组的 JSON 文本
 */
public record ModelRow(
        String providerCode,
        String modelKey,
        String displayName,
        Integer contextWindow,
        String capabilitiesJson) {
}
