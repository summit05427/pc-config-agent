package com.example.agent.model.web.dto;

import java.time.Instant;
import java.util.List;

/**
 * 管理端模型目录条目。
 *
 * @param provider        Provider 代码
 * @param modelKey        模型键
 * @param displayName     展示名
 * @param contextWindow   上下文窗口，可为空
 * @param capabilities    能力标签
 * @param capabilitySource 能力来源：catalog / verified
 * @param verifiedAt      最近一次能力验证时间，可为空
 * @param enabled         模型是否启用
 * @param providerEnabled Provider 是否启用；为 false 时即使模型启用也不可用
 * @param latestPricing   最新一条定价版本，未配置时为 {@code null}
 */
public record AdminModelSummaryResponse(
        String provider,
        String modelKey,
        String displayName,
        Integer contextWindow,
        List<String> capabilities,
        String capabilitySource,
        Instant verifiedAt,
        boolean enabled,
        boolean providerEnabled,
        AdminModelPricingResponse latestPricing) {
}
