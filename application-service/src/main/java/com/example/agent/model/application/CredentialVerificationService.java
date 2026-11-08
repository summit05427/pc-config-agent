package com.example.agent.model.application;

import com.example.agent.identity.application.AuthAuditRecorder;
import com.example.agent.identity.domain.AuthAuditEvent;
import com.example.agent.model.domain.CredentialMasker;
import com.example.agent.model.domain.CredentialVerificationOutcome;
import com.example.agent.model.domain.EncryptedCredential;
import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.model.domain.ProviderConnectionView;
import com.example.agent.model.infrastructure.GatewayCredentialProbe;
import com.example.agent.model.infrastructure.ProviderConnectionStore;
import com.example.agent.shared.error.BusinessException;
import java.time.Clock;
import java.time.OffsetDateTime;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 凭证验证的唯一入口。
 *
 * <p>一次验证完成：读取连接与活跃凭证、本地完整性校验、上游探测、结果分类、
 * 成功时回写两行状态、失败时统一写审计。调用方只把结果映射成自己的错误码，
 * 不再各自解析探测组件的内部枚举。</p>
 *
 * <p>明文密钥只在本类方法栈内存在，不写日志、不返回给调用方；日志只记录
 * 连接标识、用户标识、Provider 与结果分类。</p>
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class CredentialVerificationService {

    private final ProviderConnectionStore connectionStore;
    private final ProviderCredentialCipher cipher;
    private final GatewayCredentialProbe probe;
    private final AuthAuditRecorder auditRecorder;
    private final Clock modelRuntimeUtcClock;
    private final TransactionTemplate transactionTemplate;

    /**
     * 验证一条连接的当前活跃凭证。
     *
     * @param userPublicId 用户公开 ID
     * @param connectionId 连接标识
     * @return 验证分类结果；只有 {@code VERIFIED} 时会回写状态
     * @throws BusinessException 连接或活跃凭证不存在时 404；接入地址被安全策略拒绝时 400
     */
    public CredentialVerificationOutcome verify(UUID userPublicId, UUID connectionId) {
        ProviderConnectionView view = requireConnection(userPublicId, connectionId);
        EncryptedCredential credential = requireCredential(userPublicId, connectionId);
        String plaintext = decryptOrNull(credential.ciphertext());
        if (plaintext == null || !CredentialMasker.mask(plaintext).equals(credential.maskedHint())) {
            return recordFailure(userPublicId, connectionId, view.provider(),
                    CredentialVerificationOutcome.CORRUPTED);
        }
        CredentialVerificationOutcome outcome = classify(
                probeUpstream(userPublicId, connectionId, view, plaintext));
        if (outcome != CredentialVerificationOutcome.VERIFIED) {
            return recordFailure(userPublicId, connectionId, view.provider(), outcome);
        }
        markVerified(userPublicId, connectionId, credential.id());
        auditRecorder.recordForUser(AuthAuditEvent.MODEL_CREDENTIAL_VERIFIED, userPublicId);
        log.info("BYOK 凭证验证通过 connectionId={} userId={} provider={}",
                connectionId, userPublicId, view.provider());
        return CredentialVerificationOutcome.VERIFIED;
    }

    private ProviderConnectionView requireConnection(UUID userPublicId, UUID connectionId) {
        ProviderConnectionView view = connectionStore.findActiveView(userPublicId, connectionId);
        if (view == null) {
            throw new BusinessException(ModelErrorCode.CONNECTION_NOT_FOUND);
        }
        return view;
    }

    private EncryptedCredential requireCredential(UUID userPublicId, UUID connectionId) {
        EncryptedCredential credential = connectionStore.findActiveCredential(userPublicId, connectionId);
        if (credential == null) {
            throw new BusinessException(ModelErrorCode.CONNECTION_NOT_FOUND);
        }
        return credential;
    }

    /**
     * 解密失败统一折叠为「密文损坏」结果，由调用方映射成 500；探测阶段仍保留原错误码。
     */
    private String decryptOrNull(String ciphertext) {
        try {
            return cipher.decrypt(ciphertext);
        } catch (BusinessException ex) {
            return null;
        }
    }

    /**
     * 出站探测放在事务外，外部 HTTP 的超时与抖动不占用数据库连接和行锁。
     */
    private GatewayCredentialProbe.Outcome probeUpstream(
            UUID userPublicId, UUID connectionId, ProviderConnectionView view, String plaintext) {
        try {
            return probe.probe(view.provider(), view.baseUrl(), plaintext);
        } catch (BusinessException ex) {
            auditRecorder.recordForUser(AuthAuditEvent.MODEL_CREDENTIAL_VERIFY_FAILED, userPublicId);
            log.warn("BYOK 凭证验证被安全策略拒绝 connectionId={} userId={} provider={} reason={}",
                    connectionId, userPublicId, view.provider(), ex.getClass().getSimpleName());
            throw ex;
        }
    }

    private static CredentialVerificationOutcome classify(GatewayCredentialProbe.Outcome outcome) {
        return switch (outcome) {
            case VERIFIED -> CredentialVerificationOutcome.VERIFIED;
            case REJECTED -> CredentialVerificationOutcome.REJECTED;
            case UNAVAILABLE -> CredentialVerificationOutcome.UNAVAILABLE;
        };
    }

    private CredentialVerificationOutcome recordFailure(
            UUID userPublicId, UUID connectionId, String providerCode, CredentialVerificationOutcome outcome) {
        auditRecorder.recordForUser(AuthAuditEvent.MODEL_CREDENTIAL_VERIFY_FAILED, userPublicId);
        log.warn("BYOK 凭证验证未通过 connectionId={} userId={} provider={} outcome={}",
                connectionId, userPublicId, providerCode, outcome);
        return outcome;
    }

    /**
     * 两次状态更新放在同一短事务内，避免出现「连接已验证、凭证仍未验证」的中间态。
     */
    private void markVerified(UUID userPublicId, UUID connectionId, UUID credentialId) {
        OffsetDateTime verifiedAt = OffsetDateTime.now(modelRuntimeUtcClock);
        transactionTemplate.executeWithoutResult(status -> connectionStore.markVerified(
                userPublicId, connectionId, credentialId, verifiedAt));
    }
}
