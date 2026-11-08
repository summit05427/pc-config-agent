package com.example.agent.model.web.dto;

import com.example.agent.model.infrastructure.AdminConnectionRow;
import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * 管理端模型连接只读响应。
 *
 * <p>任何情况下都不含明文密钥或密文；凭证只有掩码与状态。</p>
 *
 * @param id             连接标识
 * @param userId         用户公开 ID
 * @param username       用户登录名，可为空
 * @param displayName    用户展示名，可为空
 * @param provider       Provider 代码
 * @param providerName   Provider 展示名
 * @param baseUrl        接入地址
 * @param status         连接状态
 * @param lastVerifiedAt 最近一次上游验证时间，可为空
 * @param createdAt      创建时间
 * @param credential     当前有效凭证摘要，可为空
 */
public record AdminModelConnectionResponse(
        UUID id,
        UUID userId,
        String username,
        String displayName,
        String provider,
        String providerName,
        String baseUrl,
        String status,
        OffsetDateTime lastVerifiedAt,
        OffsetDateTime createdAt,
        CredentialSummary credential) {

    /**
     * @param row 连接只读行
     * @return 对外响应
     */
    public static AdminModelConnectionResponse from(AdminConnectionRow row) {
        CredentialSummary credential = row.credentialId() == null
                ? null
                : new CredentialSummary(
                        row.credentialId(),
                        row.maskedHint(),
                        row.credentialStatus(),
                        row.credentialCreatedAt());
        return new AdminModelConnectionResponse(
                row.id(), row.userPublicId(), row.username(), row.displayName(),
                row.providerCode(), row.providerName(), row.baseUrl(), row.status(),
                row.lastVerifiedAt(), row.createdAt(), credential);
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
