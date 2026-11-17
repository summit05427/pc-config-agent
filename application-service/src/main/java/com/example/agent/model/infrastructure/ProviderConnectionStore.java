package com.example.agent.model.infrastructure;

import com.example.agent.model.domain.EncryptedCredential;
import com.example.agent.model.domain.ProviderConnectionView;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/**
 * BYOK 连接与凭证的读写入口。
 *
 * <p>凭证从属于连接，两张表放在同一个 Store，避免两处重复映射同一行。
 * 所有查询仍把 {@code user_public_id} 条件下推到 SQL，这里不做「先查后判」。</p>
 */
@Component
@RequiredArgsConstructor
public class ProviderConnectionStore {

    private final ProviderConnectionMapper connectionMapper;
    private final ProviderCredentialMapper credentialMapper;

    public ProviderConnectionView findActiveView(UUID userPublicId, UUID connectionId) {
        return toView(connectionMapper.findActiveViewById(connectionId, userPublicId));
    }

    public ProviderConnectionView findActiveViewByProvider(UUID userPublicId, String providerCode) {
        return toView(connectionMapper.findActiveViewByProvider(userPublicId, providerCode));
    }

    public List<ProviderConnectionView> listActive(UUID userPublicId) {
        return connectionMapper.findActiveViewsByUser(userPublicId).stream()
                .map(ProviderConnectionStore::toView)
                .toList();
    }

    public long countActive(UUID userPublicId) {
        return connectionMapper.countActiveByUser(userPublicId);
    }

    public List<ProviderConnectionView> listActivePage(UUID userPublicId, long offset, int limit) {
        return connectionMapper.findActiveViewsPageByUser(userPublicId, offset, limit).stream()
                .map(ProviderConnectionStore::toView)
                .toList();
    }

    public void insertConnection(
            UUID id, UUID userPublicId, String providerCode, String baseUrl, String status) {
        connectionMapper.insert(new ProviderConnectionRow(
                id, userPublicId, providerCode, baseUrl, status, null, null, null));
    }

    public void insertCredential(EncryptedCredential credential) {
        credentialMapper.insert(new ProviderCredentialRow(
                credential.id(), credential.connectionId(), credential.userPublicId(), credential.credentialType(),
                credential.ciphertext(), credential.keyVersion(), credential.maskedHint(),
                credential.status(), null, null));
    }

    public EncryptedCredential findActiveCredential(UUID userPublicId, UUID connectionId) {
        return toCredential(credentialMapper.findActiveByConnection(connectionId, userPublicId));
    }

    public EncryptedCredential findActiveCredentialById(UUID userPublicId, UUID credentialId) {
        return toCredential(credentialMapper.findActiveById(credentialId, userPublicId));
    }

    public int updateBaseUrl(UUID userPublicId, UUID connectionId, String baseUrl, OffsetDateTime updatedAt) {
        return connectionMapper.updateBaseUrl(connectionId, userPublicId, baseUrl, updatedAt);
    }

    public void revokeCredentials(UUID userPublicId, UUID connectionId, OffsetDateTime revokedAt) {
        credentialMapper.markRevokedByConnection(connectionId, userPublicId, revokedAt);
    }

    public int markDeleted(UUID userPublicId, UUID connectionId, OffsetDateTime updatedAt) {
        return connectionMapper.markDeleted(connectionId, userPublicId, updatedAt);
    }

    /**
     * 连接与凭证两行一起标记通过；从签名上就不允许只更新其中一行。
     */
    public void markVerified(
            UUID userPublicId, UUID connectionId, UUID credentialId, OffsetDateTime verifiedAt) {
        connectionMapper.markVerified(connectionId, userPublicId, verifiedAt);
        credentialMapper.markVerified(credentialId, userPublicId);
    }

    /**
     * 凭证被上游拒绝时标记失效：凭证置 INVALID，连接清空最近验证时间。
     */
    public void markInvalid(
            UUID userPublicId, UUID connectionId, UUID credentialId, OffsetDateTime updatedAt) {
        credentialMapper.markInvalid(credentialId, userPublicId);
        connectionMapper.clearVerifiedAt(connectionId, userPublicId, updatedAt);
    }

    /**
     * 只凭凭证 ID 标记失效：使用明细回写时任务行只有凭证 ID，没有连接 ID。
     *
     * @param userPublicId 用户公开 ID
     * @param credentialId 凭证标识
     * @param updatedAt    更新时间
     */
    public void markInvalidByCredential(
            UUID userPublicId, UUID credentialId, OffsetDateTime updatedAt) {
        credentialMapper.markInvalid(credentialId, userPublicId);
        connectionMapper.clearVerifiedAtByCredential(credentialId, userPublicId, updatedAt);
    }

    private static ProviderConnectionView toView(ProviderConnectionViewRow row) {
        if (row == null) {
            return null;
        }
        ProviderConnectionView.CredentialView credential = row.credentialId() == null
                ? null
                : new ProviderConnectionView.CredentialView(
                        row.credentialId(), row.maskedHint(), row.credentialStatus(), row.credentialCreatedAt());
        return new ProviderConnectionView(
                row.id(), row.providerCode(), row.providerName(), row.baseUrl(),
                row.status(), row.lastVerifiedAt(), row.createdAt(), credential);
    }

    private static EncryptedCredential toCredential(ProviderCredentialRow row) {
        if (row == null) {
            return null;
        }
        return new EncryptedCredential(
                row.id(), row.connectionId(), row.userPublicId(), row.credentialType(), row.ciphertext(),
                row.keyVersion(), row.maskedHint(), row.status());
    }
}
