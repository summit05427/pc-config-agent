package com.example.agent.model.application;

import com.example.agent.model.domain.CredentialLease;
import com.example.agent.model.domain.EncryptedCredential;
import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.model.domain.RuntimeTaskSnapshot;
import com.example.agent.model.infrastructure.ProviderConnectionStore;
import com.example.agent.model.infrastructure.RuntimeTaskStore;
import com.example.agent.shared.error.BusinessException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.HexFormat;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * BYOK 凭证兑换：同一个运行时任务最多成功兑换一次。
 *
 * <p>兑换与任务创建必须分开调用，任务响应永远不含密钥；兑换使用条件 UPDATE
 * （{@code leased_at IS NULL}）保证并发下只有一次成功。明文密钥不落库、不进日志、
 * 不进入任何审计字段。</p>
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class CredentialLeaseService {

    static final String CREDENTIAL_SOURCE_BYOK = "BYOK";

    private static final String TASK_STATUS_ACTIVE = "ACTIVE";

    private static final int LOG_HASH_PREFIX_LENGTH = 8;

    private final ModelRuntimeGuard runtimeGuard;
    private final RuntimeTaskStore runtimeTaskStore;
    private final ProviderConnectionStore connectionStore;
    private final ProviderCredentialCipher cipher;
    private final Clock modelRuntimeUtcClock;

    /**
     * 兑换任务对应的 BYOK 明文凭证。
     *
     * @param taskId 任务标识
     * @return 明文凭证与有效期
     * @throws BusinessException 任务不存在或已过期 404、非 BYOK 任务 409、
     *                           已兑换 409、凭证撤销 401
     */
    @Transactional
    public CredentialLease lease(UUID taskId) {
        runtimeGuard.requireEnabled();
        RuntimeTaskSnapshot task = runtimeTaskStore.findById(taskId);
        OffsetDateTime now = OffsetDateTime.now(modelRuntimeUtcClock);
        if (task == null || !TASK_STATUS_ACTIVE.equals(task.status()) || !task.expiresAt().isAfter(now)) {
            throw new BusinessException(ModelErrorCode.TASK_NOT_FOUND);
        }
        if (!CREDENTIAL_SOURCE_BYOK.equals(task.credentialSource())) {
            throw new BusinessException(ModelErrorCode.LEASE_NOT_BYOK);
        }
        if (task.credentialId() == null) {
            throw new BusinessException(ModelErrorCode.CREDENTIAL_REVOKED);
        }
        EncryptedCredential credential =
                connectionStore.findActiveCredentialById(task.userPublicId(), task.credentialId());
        if (credential == null) {
            throw new BusinessException(ModelErrorCode.CREDENTIAL_REVOKED);
        }
        String secret = cipher.decrypt(credential.ciphertext());
        // 先解密再标记：密文损坏时任务不消耗，重试仍会得到同一个明确错误
        if (runtimeTaskStore.markLeased(task.id(), now) == 0) {
            throw new BusinessException(ModelErrorCode.CREDENTIAL_LEASE_CONSUMED);
        }
        long expiresIn = Math.max(1, Duration.between(now, task.expiresAt()).toSeconds());
        log.info("BYOK 凭证已兑换 taskId={} credential={}", task.id(), logHash(task.credentialId()));
        return new CredentialLease(credential.credentialType(), secret, expiresIn);
    }

    /**
     * 日志只输出凭证标识的哈希前缀，避免可反查的标识直接落盘。
     */
    private static String logHash(UUID credentialId) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(credentialId.toString().getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest).substring(0, LOG_HASH_PREFIX_LENGTH);
        } catch (NoSuchAlgorithmException ex) {
            return "hash-unavailable";
        }
    }
}
