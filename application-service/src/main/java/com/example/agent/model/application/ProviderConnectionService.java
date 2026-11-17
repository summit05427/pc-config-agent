package com.example.agent.model.application;

import com.example.agent.identity.application.AuthAuditRecorder;
import com.example.agent.identity.domain.AuthAuditEvent;
import com.example.agent.model.domain.CredentialMasker;
import com.example.agent.model.domain.CredentialVerificationOutcome;
import com.example.agent.model.domain.EncryptedCredential;
import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.model.domain.ProviderConnectionView;
import com.example.agent.model.domain.ProviderDescriptor;
import com.example.agent.model.infrastructure.OutboundHostGuard;
import com.example.agent.model.infrastructure.ProviderCatalogStore;
import com.example.agent.model.infrastructure.ProviderConnectionStore;
import com.example.agent.shared.api.PageQuery;
import com.example.agent.shared.api.PageResult;
import com.example.agent.shared.config.ModelRuntimeProperties;
import com.example.agent.shared.error.BusinessException;
import java.time.Clock;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * BYOK 连接与凭证服务。
 *
 * <p>明文密钥只在本服务的单个方法栈内出现：加密后立即丢弃，响应只返回掩码；
 * 日志只记录连接标识与 Provider，不记录密钥、密文或掩码以外的任何内容。</p>
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ProviderConnectionService {

    static final String CONNECTION_STATUS_ACTIVE = "ACTIVE";

    static final String CREDENTIAL_TYPE_API_KEY = "api_key";

    static final String CREDENTIAL_STATUS_UNVERIFIED = "UNVERIFIED";

    private final ModelRuntimeGuard runtimeGuard;
    private final ProviderCatalogStore providerCatalogStore;
    private final ProviderConnectionStore connectionStore;
    private final ProviderCredentialCipher cipher;
    private final OutboundHostGuard outboundHostGuard;
    private final ModelCredentialVerifyRateLimiter verifyRateLimiter;
    private final AuthAuditRecorder auditRecorder;
    private final CredentialVerificationService verificationService;
    private final ModelRuntimeProperties properties;
    private final Clock modelRuntimeUtcClock;
    private final TransactionTemplate transactionTemplate;

    /**
     * 列出当前用户的 ACTIVE 连接。
     *
     * @param userPublicId 用户公开 ID
     * @return 连接视图，按创建时间倒序
     * @throws BusinessException BYOK 未启用时 404
     */
    @Transactional(readOnly = true)
    public List<ProviderConnectionView> list(UUID userPublicId) {
        runtimeGuard.requireByokEnabled();
        return connectionStore.listActive(userPublicId);
    }

    /**
     * 分页列出当前用户的 ACTIVE 连接。
     *
     * @param userPublicId 用户公开 ID
     * @param query        分页参数
     * @return 当前页连接视图与总数
     * @throws BusinessException BYOK 未启用时 404
     */
    @Transactional(readOnly = true)
    public PageResult<ProviderConnectionView> list(UUID userPublicId, PageQuery query) {
        runtimeGuard.requireByokEnabled();
        long total = connectionStore.countActive(userPublicId);
        if (query.offset() >= total) {
            return PageResult.of(List.of(), total, query);
        }
        List<ProviderConnectionView> connections =
                connectionStore.listActivePage(userPublicId, query.offset(), query.getSize());
        return PageResult.of(connections, total, query);
    }

    /**
     * 创建连接并保存加密凭证。
     *
     * @param userPublicId  用户公开 ID
     * @param providerCode  Provider 代码
     * @param requestedUrl  自定义接入地址，为空表示交给网关使用 Provider 官方默认地址
     * @param apiKey        明文密钥，仅在本方法内存在
     * @return 不含明文的连接视图
     * @throws BusinessException Provider 不存在 400、地址非法 400、重复连接 409、BYOK 未启用 404
     */
    public ProviderConnectionView create(
            UUID userPublicId, String providerCode, String requestedUrl, String apiKey) {
        runtimeGuard.requireByokEnabled();
        ProviderDescriptor provider = requireSupportedProvider(providerCode.trim());
        String baseUrl = resolveBaseUrl(requestedUrl);
        String secret = apiKey == null ? "" : apiKey.trim();
        if (secret.isEmpty()) {
            throw new BusinessException(ModelErrorCode.CREDENTIAL_REQUIRED);
        }
        String ciphertext = cipher.encrypt(secret);
        String maskedHint = CredentialMasker.mask(secret);

        UUID connectionId = UUID.randomUUID();
        UUID credentialId = UUID.randomUUID();
        // 外部探测不能占用数据库事务：先用短事务落库，再出站验证并回写状态
        transactionTemplate.executeWithoutResult(status -> {
            insertConnection(connectionId, userPublicId, provider.code(), baseUrl);
            connectionStore.insertCredential(new EncryptedCredential(
                    credentialId, connectionId, userPublicId, CREDENTIAL_TYPE_API_KEY, ciphertext,
                    properties.getCredential().getKeyVersion(), maskedHint, CREDENTIAL_STATUS_UNVERIFIED));
        });
        auditRecorder.recordForUser(AuthAuditEvent.MODEL_CREDENTIAL_CREATED, userPublicId);
        log.info("BYOK 连接已创建 connectionId={} userId={} provider={}",
                connectionId, userPublicId, provider.code());

        // 创建即自动验证；失败不回滚连接，避免上游抖动导致用户重复录入
        autoVerify(userPublicId, connectionId, provider.code());
        return requireView(userPublicId, connectionId);
    }

    /**
     * 轮换密钥或调整接入地址。
     *
     * <p>旧凭证标记撤销后插入新凭证，保证同一连接始终只有一条有效凭证；
     * 地址变更会清空旧的验证时间。保存成功后自动做一次验证。</p>
     *
     * @param userPublicId  用户公开 ID
     * @param connectionId  连接标识
     * @param requestedUrl  新接入地址，为空表示沿用原地址
     * @param apiKey        新明文密钥
     * @return 更新后的连接视图
     * @throws BusinessException 连接不存在 404、Provider 不存在 400、地址非法 400、密钥为空 400
     */
    public ProviderConnectionView update(
            UUID userPublicId, UUID connectionId, String requestedUrl, String apiKey) {
        runtimeGuard.requireByokEnabled();
        ProviderConnectionView view = requireView(userPublicId, connectionId);
        ProviderDescriptor provider = requireSupportedProvider(view.provider());
        String baseUrl = resolveUpdatedBaseUrl(requestedUrl, view.baseUrl());
        String secret = apiKey == null ? "" : apiKey.trim();
        if (secret.isEmpty()) {
            throw new BusinessException(ModelErrorCode.CREDENTIAL_REQUIRED);
        }
        String ciphertext = cipher.encrypt(secret);
        String maskedHint = CredentialMasker.mask(secret);
        UUID credentialId = UUID.randomUUID();
        OffsetDateTime now = OffsetDateTime.now(modelRuntimeUtcClock);

        transactionTemplate.executeWithoutResult(status -> {
            int updated = connectionStore.updateBaseUrl(userPublicId, connectionId, baseUrl, now);
            if (updated == 0) {
                throw new BusinessException(ModelErrorCode.CONNECTION_NOT_FOUND);
            }
            connectionStore.revokeCredentials(userPublicId, connectionId, now);
            connectionStore.insertCredential(new EncryptedCredential(
                    credentialId, connectionId, userPublicId, CREDENTIAL_TYPE_API_KEY, ciphertext,
                    properties.getCredential().getKeyVersion(), maskedHint, CREDENTIAL_STATUS_UNVERIFIED));
        });
        auditRecorder.recordForUser(AuthAuditEvent.MODEL_CREDENTIAL_UPDATED, userPublicId);
        log.info("BYOK 凭证已轮换 connectionId={} userId={} provider={}",
                connectionId, userPublicId, provider.code());

        autoVerify(userPublicId, connectionId, provider.code());
        return requireView(userPublicId, connectionId);
    }

    /**
     * 校验凭证：本地密文完整性 + 真实上游探测。
     *
     * <p>先做本地校验（能解密、掩码一致），再按 {@code GET /models}（不支持时退化最小 chat）
     * 调一次 Provider。验证通过才写 {@code last_verified_at} 并把凭证置为 VERIFIED；
     * 上游明确拒绝时把凭证置为 INVALID，网络不可达则不改状态，
     * 避免把临时故障写成永久失败。</p>
     *
     * @param userPublicId 用户公开 ID
     * @param connectionId 连接标识
     * @return 更新后的连接视图
     * @throws BusinessException 连接不存在 404、密文损坏 500、凭证被拒 422、上游不可用 502
     */
    public ProviderConnectionView verify(UUID userPublicId, UUID connectionId) {
        runtimeGuard.requireByokEnabled();
        // 先限流再解密/出站：避免被当作低成本探测入口
        verifyRateLimiter.requireAllowed(userPublicId);
        CredentialVerificationOutcome outcome = verificationService.verify(userPublicId, connectionId);
        if (outcome == CredentialVerificationOutcome.CORRUPTED) {
            throw new BusinessException(ModelErrorCode.CREDENTIAL_CORRUPTED);
        }
        if (outcome == CredentialVerificationOutcome.REJECTED) {
            throw new BusinessException(ModelErrorCode.CREDENTIAL_REJECTED);
        }
        if (outcome == CredentialVerificationOutcome.UNAVAILABLE) {
            throw new BusinessException(ModelErrorCode.CREDENTIAL_VERIFY_FAILED);
        }
        return requireView(userPublicId, connectionId);
    }

    /**
     * 删除连接并撤销其凭证。
     *
     * <p>软删除而非物理删除：凭证一旦被撤销，后续任务授权与兑换必须失败，
     * 保留历史行才能对账与审计。</p>
     *
     * @param userPublicId 用户公开 ID
     * @param connectionId 连接标识
     * @throws BusinessException 连接不存在或不属于该用户时 404
     */
    @Transactional
    public void delete(UUID userPublicId, UUID connectionId) {
        runtimeGuard.requireByokEnabled();
        requireView(userPublicId, connectionId);
        OffsetDateTime now = OffsetDateTime.now(modelRuntimeUtcClock);
        int updated = connectionStore.markDeleted(userPublicId, connectionId, now);
        if (updated == 0) {
            throw new BusinessException(ModelErrorCode.CONNECTION_NOT_FOUND);
        }
        connectionStore.revokeCredentials(userPublicId, connectionId, now);
        auditRecorder.recordForUser(AuthAuditEvent.MODEL_CREDENTIAL_DELETED, userPublicId);
        log.info("BYOK 连接已删除 connectionId={} userId={}", connectionId, userPublicId);
    }

    /**
     * 创建与轮换后的自动验证：失败只记录日志，不影响连接保存。
     *
     * <p>通过/失败审计与状态回写由验证模块统一完成，这里只在异常时补一条原因日志。</p>
     */
    private void autoVerify(UUID userPublicId, UUID connectionId, String providerCode) {
        try {
            verificationService.verify(userPublicId, connectionId);
        } catch (BusinessException ex) {
            log.warn("BYOK 凭证自动验证失败 connectionId={} userId={} provider={} reason={}",
                    connectionId, userPublicId, providerCode, ex.getClass().getSimpleName());
        }
    }

    private void insertConnection(UUID connectionId, UUID userPublicId, String providerCode, String baseUrl) {
        try {
            connectionStore.insertConnection(
                    connectionId, userPublicId, providerCode, baseUrl, CONNECTION_STATUS_ACTIVE);
        } catch (DuplicateKeyException ex) {
            // 唯一索引兜底并发重复创建；异常信息可能含 SQL，不对外透传
            throw new BusinessException(ModelErrorCode.CONNECTION_EXISTS);
        }
    }

    private ProviderDescriptor requireSupportedProvider(String providerCode) {
        ProviderDescriptor provider = providerCatalogStore.findEnabledProvider(providerCode);
        if (provider == null) {
            throw new BusinessException(ModelErrorCode.PROVIDER_NOT_SUPPORTED);
        }
        return provider;
    }

    /**
     * 接入地址可选：留空表示交给网关使用该 Provider 的官方默认地址，Java 不补值。
     */
    private String resolveBaseUrl(String requestedUrl) {
        String candidate = requestedUrl == null ? "" : requestedUrl.trim();
        if (candidate.isEmpty()) {
            return "";
        }
        // DNS 解析结果也要校验，防止公网域名指向内网
        return outboundHostGuard.validate(candidate);
    }

    /**
     * 轮换地址时留空表示沿用原地址；原地址非空时同样重新过一遍 DNS 校验。
     */
    private String resolveUpdatedBaseUrl(String requestedUrl, String currentBaseUrl) {
        String candidate = requestedUrl == null ? "" : requestedUrl.trim();
        if (!candidate.isEmpty()) {
            return resolveBaseUrl(candidate);
        }
        if (currentBaseUrl == null || currentBaseUrl.isBlank()) {
            return "";
        }
        return outboundHostGuard.validate(currentBaseUrl);
    }

    private ProviderConnectionView requireView(UUID userPublicId, UUID connectionId) {
        ProviderConnectionView view = connectionStore.findActiveView(userPublicId, connectionId);
        if (view == null) {
            throw new BusinessException(ModelErrorCode.CONNECTION_NOT_FOUND);
        }
        return view;
    }
}
