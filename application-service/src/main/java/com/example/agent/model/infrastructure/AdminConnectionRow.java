package com.example.agent.model.infrastructure;

import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * 管理端连接只读行，含用户展示信息与当前有效凭证摘要。
 *
 * <p>凭证字段只含掩码与状态，密文与明文密钥都不进入查询结果。</p>
 */
public record AdminConnectionRow(
        UUID id,
        UUID userPublicId,
        String username,
        String displayName,
        String providerCode,
        String providerName,
        String baseUrl,
        String status,
        OffsetDateTime lastVerifiedAt,
        OffsetDateTime createdAt,
        UUID credentialId,
        String maskedHint,
        String credentialStatus,
        OffsetDateTime credentialCreatedAt) {
}
