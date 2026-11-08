package com.example.agent.model.domain;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * 使用明细视图，供本人用量查询使用。
 *
 * <p>不包含 {@code userPublicId}：查询已按令牌主体限定范围，响应无需再次暴露用户标识。</p>
 *
 * @param invocationId     调用唯一标识（幂等键）
 * @param taskId           运行时任务标识
 * @param threadId         会话标识
 * @param modelRole        模型角色，如 {@code conversation}
 * @param provider         Provider 代码
 * @param modelKey         模型键（不含 Provider 前缀）
 * @param credentialSource 凭证来源：{@code MANAGED} / {@code BYOK}
 * @param promptTokens     提示词 Token，上游未返回时为空
 * @param completionTokens 补全 Token，上游未返回时为空
 * @param latencyMs        调用耗时（毫秒），未知时为空
 * @param status           调用结果：{@code success} / {@code failure}
 * @param errorType        失败时的错误类型，可为空
 * @param estimatedCost    预估费用；{@code costStatus} 非 {@code ESTIMATED} 时为空
 * @param costStatus       成本状态：{@code ESTIMATED} / {@code UNKNOWN} / {@code BYOK_NOT_BILLED}
 * @param costBearer       成本承担方：{@code PLATFORM} / {@code USER}
 * @param currency         费用币种，未估算时为空
 * @param occurredAt       调用发生时间
 */
public record ModelUsageView(
        UUID invocationId,
        UUID taskId,
        String threadId,
        String modelRole,
        String provider,
        String modelKey,
        String credentialSource,
        Integer promptTokens,
        Integer completionTokens,
        Integer latencyMs,
        String status,
        String errorType,
        BigDecimal estimatedCost,
        String costStatus,
        String costBearer,
        String currency,
        OffsetDateTime occurredAt) {
}
