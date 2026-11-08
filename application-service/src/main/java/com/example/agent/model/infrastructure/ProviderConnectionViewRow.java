package com.example.agent.model.infrastructure;

import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * 连接 + 当前有效凭证的联表视图。
 *
 * <p>一次查询返回列表所需全部字段，避免按连接逐条查凭证造成 N+1。</p>
 *
 * @param id                  连接标识
 * @param providerCode        Provider 代码
 * @param providerName        Provider 展示名
 * @param baseUrl             接入地址
 * @param status              连接状态
 * @param lastVerifiedAt      最近一次上游验证时间
 * @param createdAt           创建时间
 * @param credentialId        当前有效凭证标识，可为空
 * @param maskedHint          凭证掩码
 * @param credentialStatus    凭证状态
 * @param credentialCreatedAt 凭证创建时间
 */
public record ProviderConnectionViewRow(
        UUID id,
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
