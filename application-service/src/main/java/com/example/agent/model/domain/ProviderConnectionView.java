package com.example.agent.model.domain;

import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * 连接视图，面向浏览器的唯一形态。
 *
 * <p>永不包含明文密钥；{@code credential} 只有掩码与状态，也不提供回读接口。</p>
 *
 * @param id             连接标识
 * @param provider       Provider 代码
 * @param providerName   Provider 展示名
 * @param baseUrl        接入地址
 * @param status         连接状态
 * @param lastVerifiedAt 最近一次上游验证时间，可为空
 * @param createdAt      创建时间
 * @param credential     当前有效凭证摘要，可为空
 */
public record ProviderConnectionView(
        UUID id,
        String provider,
        String providerName,
        String baseUrl,
        String status,
        OffsetDateTime lastVerifiedAt,
        OffsetDateTime createdAt,
        CredentialView credential) {

    /**
     * 凭证摘要。
     *
     * @param id         凭证标识
     * @param maskedHint 掩码
     * @param status     凭证状态
     * @param createdAt  创建时间
     */
    public record CredentialView(
            UUID id,
            String maskedHint,
            String status,
            OffsetDateTime createdAt) {
    }
}
