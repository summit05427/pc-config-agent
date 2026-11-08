package com.example.agent.model.infrastructure;

import java.time.OffsetDateTime;

/**
 * 管理端模型目录行。
 *
 * <p>与面向用户的 {@link ModelRow} 不同，这里包含停用状态与 Provider 启用状态，
 * 供管理端判断「模型本身停用」与「Provider 被停用导致不可用」两种不同原因。</p>
 *
 * @param providerCode     Provider 代码
 * @param modelKey         Provider 侧模型标识
 * @param displayName      展示名
 * @param contextWindow    上下文窗口，可为空
 * @param capabilitiesJson 能力元数据 JSON 文本，由服务层解析
 * @param capabilitySource 能力来源：catalog / verified
 * @param verifiedAt       最近一次能力验证时间，可为空
 * @param enabled          模型是否启用
 * @param providerEnabled  Provider 是否启用
 */
public record AdminModelRow(
        String providerCode,
        String modelKey,
        String displayName,
        Integer contextWindow,
        String capabilitiesJson,
        String capabilitySource,
        OffsetDateTime verifiedAt,
        Boolean enabled,
        Boolean providerEnabled) {
}
