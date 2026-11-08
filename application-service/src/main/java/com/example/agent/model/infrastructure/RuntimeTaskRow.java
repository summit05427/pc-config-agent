package com.example.agent.model.infrastructure;

import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * 运行时任务行。
 *
 * @param id               任务主键
 * @param userPublicId     用户公开 ID（JWT {@code sub}）
 * @param threadId         会话线程标识
 * @param requestedModel   请求指定的模型，可为空
 * @param resolvedModel    解析后的模型引用
 * @param credentialSource 凭证来源
 * @param credentialId     BYOK 凭证 ID，非 BYOK 任务为空
 * @param baseUrl          BYOK 接入地址快照，MANAGED 任务为空
 * @param status           任务状态
 * @param expiresAt        过期时间
 * @param createdAt        创建时间
 * @param idempotencyKey   调用方幂等键，为空表示未启用幂等
 */
public record RuntimeTaskRow(
        UUID id,
        UUID userPublicId,
        String threadId,
        String requestedModel,
        String resolvedModel,
        String credentialSource,
        UUID credentialId,
        String baseUrl,
        String status,
        OffsetDateTime expiresAt,
        OffsetDateTime createdAt,
        String idempotencyKey) {
}
