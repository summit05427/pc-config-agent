package com.example.agent.model.infrastructure;

import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * Provider 凭证行（只含密文）。
 *
 * @param id            凭证标识
 * @param connectionId  所属连接
 * @param userPublicId  用户公开 ID
 * @param credentialType 凭证类型，首版固定 {@code api_key}
 * @param ciphertext    密文，格式见 V12 迁移脚本
 * @param keyVersion    加密主密钥版本；用包装类型，MyBatis 构造器映射不认原始 int
 * @param maskedHint    掩码提示
 * @param status        凭证状态：UNVERIFIED / VERIFIED / REVOKED
 * @param createdAt     创建时间
 * @param revokedAt     撤销时间，可为空
 */
public record ProviderCredentialRow(
        UUID id,
        UUID connectionId,
        UUID userPublicId,
        String credentialType,
        String ciphertext,
        Integer keyVersion,
        String maskedHint,
        String status,
        OffsetDateTime createdAt,
        OffsetDateTime revokedAt) {
}
