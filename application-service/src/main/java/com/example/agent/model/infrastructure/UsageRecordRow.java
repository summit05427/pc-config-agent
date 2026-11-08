package com.example.agent.model.infrastructure;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * 使用明细行。
 *
 * <p>与 {@code UsageRecordInput} 的差异：这里带上服务端解析出的 {@code userPublicId}，
 * 不信任上报方的用户字段；费用字段全部由服务端依据定价表计算，上报方不可指定。</p>
 */
public record UsageRecordRow(
        UUID invocationId,
        UUID taskId,
        UUID userPublicId,
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
