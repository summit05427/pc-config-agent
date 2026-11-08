package com.example.agent.model.web.dto;

import com.example.agent.model.domain.ProviderConnectionView;
import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * 连接响应，任何情况下都不含明文密钥。
 *
 * @param id             连接标识
 * @param provider       Provider 代码
 * @param providerName   Provider 展示名
 * @param baseUrl        接入地址
 * @param status         连接状态
 * @param lastVerifiedAt 最近一次上游验证时间，可为空
 * @param createdAt      创建时间
 * @param credential     凭证摘要，可为空
 */
public record ModelConnectionResponse(
        UUID id,
        String provider,
        String providerName,
        String baseUrl,
        String status,
        OffsetDateTime lastVerifiedAt,
        OffsetDateTime createdAt,
        CredentialSummary credential) {

    /**
     * @param view 领域视图
     * @return 对外响应
     */
    public static ModelConnectionResponse from(ProviderConnectionView view) {
        CredentialSummary credential = view.credential() == null
                ? null
                : new CredentialSummary(
                        view.credential().id(),
                        view.credential().maskedHint(),
                        view.credential().status(),
                        view.credential().createdAt());
        return new ModelConnectionResponse(
                view.id(), view.provider(), view.providerName(), view.baseUrl(),
                view.status(), view.lastVerifiedAt(), view.createdAt(), credential);
    }

    /**
     * 凭证摘要：只有掩码与状态。
     *
     * @param id         凭证标识
     * @param maskedHint 掩码
     * @param status     凭证状态
     * @param createdAt  创建时间
     */
    public record CredentialSummary(
            UUID id,
            String maskedHint,
            String status,
            OffsetDateTime createdAt) {
    }
}
