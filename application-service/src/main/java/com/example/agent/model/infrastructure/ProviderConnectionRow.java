package com.example.agent.model.infrastructure;

import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * Provider 连接行（不含密钥）。
 *
 * @param id             连接标识，应用层生成
 * @param userPublicId   用户公开 ID
 * @param providerCode   Provider 代码
 * @param baseUrl        接入地址
 * @param status         连接状态：ACTIVE / DELETED
 * @param lastVerifiedAt 最近一次上游验证时间，可为空
 * @param createdAt      创建时间
 * @param updatedAt      更新时间
 */
public record ProviderConnectionRow(
        UUID id,
        UUID userPublicId,
        String providerCode,
        String baseUrl,
        String status,
        OffsetDateTime lastVerifiedAt,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt) {
}
