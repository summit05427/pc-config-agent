package com.example.agent.model.infrastructure;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * 管理端使用明细行，含用户展示信息。
 *
 * <p>用户标识来自任务行与用户表联查，调用方无法通过参数伪造归属；
 * 不返回内部自增主键，只返回 {@code public_id} 与登录名。</p>
 */
public record AdminUsageRow(
        UUID invocationId,
        UUID taskId,
        UUID userPublicId,
        String username,
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
