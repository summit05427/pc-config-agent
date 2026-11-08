package com.example.agent.model.web.dto;

import com.example.agent.model.infrastructure.AdminUsageRow;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * 管理端单条使用明细响应。
 *
 * <p>与用户侧响应的差异：额外返回用户公开 ID 与展示名，便于运营定位；
 * 仍不返回内部自增主键、对话内容与任何凭证信息。</p>
 */
public record AdminModelUsageItemResponse(
        UUID invocationId,
        UUID taskId,
        UUID userId,
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

    /**
     * @param row 使用明细行
     * @return 对外响应对象
     */
    public static AdminModelUsageItemResponse from(AdminUsageRow row) {
        return new AdminModelUsageItemResponse(
                row.invocationId(), row.taskId(), row.userPublicId(), row.username(),
                row.threadId(), row.modelRole(), row.provider(), row.modelKey(),
                row.credentialSource(), row.promptTokens(), row.completionTokens(),
                row.latencyMs(), row.status(), row.errorType(), row.estimatedCost(),
                row.costStatus(), row.costBearer(), row.currency(), row.occurredAt());
    }
}
