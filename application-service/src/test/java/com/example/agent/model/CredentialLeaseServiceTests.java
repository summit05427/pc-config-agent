package com.example.agent.model;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.example.agent.model.application.CredentialKeyRing;
import com.example.agent.model.application.CredentialLeaseService;
import com.example.agent.model.application.ModelRuntimeGuard;
import com.example.agent.model.application.ProviderCredentialCipher;
import com.example.agent.model.domain.CredentialLease;
import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.model.infrastructure.ProviderConnectionMapper;
import com.example.agent.model.infrastructure.ProviderConnectionStore;
import com.example.agent.model.infrastructure.ProviderCredentialMapper;
import com.example.agent.model.infrastructure.ProviderCredentialRow;
import com.example.agent.model.infrastructure.RuntimeTaskMapper;
import com.example.agent.model.infrastructure.RuntimeTaskRow;
import com.example.agent.model.infrastructure.RuntimeTaskStore;
import com.example.agent.shared.config.ModelRuntimeProperties;
import com.example.agent.shared.error.BusinessException;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 一次性凭证兑换单测：一次性语义、过期、归属与撤销都在不启容器的情况下验证。
 *
 * <p>关键不变量：明文只在成功兑换时返回；任何失败路径都不应把 {@code leased_at} 写脏，
 * 否则用户重试会拿到「已兑换」而不是真实原因。</p>
 */
@ExtendWith(MockitoExtension.class)
class CredentialLeaseServiceTests {

    private static final Instant NOW = Instant.parse("2026-10-30T08:00:00Z");

    private static final Clock CLOCK = Clock.fixed(NOW, ZoneOffset.UTC);

    private static final OffsetDateTime NOW_OFFSET = OffsetDateTime.now(CLOCK);

    private static final OffsetDateTime EXPIRES_AT = NOW_OFFSET.plusMinutes(10);

    private static final UUID USER_ID = UUID.fromString("6f5a0b36-64c6-4f38-8a9d-53e1a2c9a742");

    private static final UUID TASK_ID = UUID.fromString("9d2a6b4a-1c58-4d9a-9a54-2f6a8c1f0b21");

    private static final UUID CREDENTIAL_ID = UUID.fromString("8c7d6e5f-4a3b-2c1d-9e8f-7a6b5c4d3e2f");

    private static final UUID CONNECTION_ID = UUID.fromString("2a1f6b0e-5d3c-4b8a-9e7f-1c2d3e4f5a6b");

    private static final String SECRET = "sk-test-1234567890";

    private static final String MASTER_KEY = Base64.getEncoder()
            .encodeToString("0123456789abcdef0123456789abcdef".getBytes(StandardCharsets.UTF_8));

    @Mock
    private RuntimeTaskMapper runtimeTaskMapper;

    @Mock
    private ProviderCredentialMapper credentialMapper;

    @Mock
    private ProviderConnectionMapper connectionMapper;

    private ProviderCredentialCipher cipher;

    private ModelRuntimeProperties properties;

    private CredentialLeaseService service;

    @BeforeEach
    void setUp() {
        properties = new ModelRuntimeProperties();
        properties.setRuntimeEnabled(true);
        properties.setByokEnabled(true);
        properties.getCredential().setMasterKey(MASTER_KEY);
        properties.getCredential().setKeyVersion(1);
        cipher = new ProviderCredentialCipher(new CredentialKeyRing(properties));
        // 真实 Store 包住被 mock 的 mapper，保留原有对底层调用的断言
        service = new CredentialLeaseService(
                new ModelRuntimeGuard(properties),
                new RuntimeTaskStore(runtimeTaskMapper),
                new ProviderConnectionStore(connectionMapper, credentialMapper),
                cipher, CLOCK);
    }

    @Test
    void lease_shouldReturnPlaintextAndRemainingExpiry_whenTaskIsByokAndCredentialActive() {
        when(runtimeTaskMapper.findById(TASK_ID)).thenReturn(byokTask(CREDENTIAL_ID));
        when(credentialMapper.findActiveById(CREDENTIAL_ID, USER_ID)).thenReturn(credential(SECRET));
        when(runtimeTaskMapper.markLeased(TASK_ID, NOW_OFFSET)).thenReturn(1);

        CredentialLease lease = service.lease(TASK_ID);

        assertThat(lease.credentialType()).isEqualTo("api_key");
        assertThat(lease.secret()).isEqualTo(SECRET);
        assertThat(lease.expiresIn()).isEqualTo(600);
        // toString 覆盖是为了防止调试输出把明文密钥写进日志
        assertThat(lease.toString()).doesNotContain(SECRET);
        verify(runtimeTaskMapper).markLeased(TASK_ID, NOW_OFFSET);
    }

    @Test
    void lease_shouldReturnNotFound_whenTaskDoesNotExist() {
        when(runtimeTaskMapper.findById(TASK_ID)).thenReturn(null);

        assertLeaseFails(ModelErrorCode.TASK_NOT_FOUND);
        verify(credentialMapper, never()).findActiveById(any(), any());
        verify(runtimeTaskMapper, never()).markLeased(any(), any());
    }

    @Test
    void lease_shouldReturnNotFound_whenTaskIsExpired() {
        RuntimeTaskRow expired = new RuntimeTaskRow(
                TASK_ID, USER_ID, "t-1", null, "openai:gpt-4o-mini", "BYOK", CREDENTIAL_ID,
                "https://byok.example.com/v1", "ACTIVE", NOW_OFFSET.minusMinutes(1), NOW_OFFSET.minusMinutes(11), null);
        when(runtimeTaskMapper.findById(TASK_ID)).thenReturn(expired);

        assertLeaseFails(ModelErrorCode.TASK_NOT_FOUND);
        verify(runtimeTaskMapper, never()).markLeased(any(), any());
    }

    @Test
    void lease_shouldReturnNotFound_whenTaskIsNotActive() {
        RuntimeTaskRow revoked = new RuntimeTaskRow(
                TASK_ID, USER_ID, "t-1", null, "openai:gpt-4o-mini", "BYOK", CREDENTIAL_ID,
                "https://byok.example.com/v1", "REVOKED", EXPIRES_AT, NOW_OFFSET, null);
        when(runtimeTaskMapper.findById(TASK_ID)).thenReturn(revoked);

        assertLeaseFails(ModelErrorCode.TASK_NOT_FOUND);
        verify(runtimeTaskMapper, never()).markLeased(any(), any());
    }

    @Test
    void lease_shouldRejectManagedTask() {
        RuntimeTaskRow managed = new RuntimeTaskRow(
                TASK_ID, USER_ID, "t-1", null, "openai:gpt-4o-mini", "MANAGED", null, null,
                "ACTIVE", EXPIRES_AT, NOW_OFFSET, null);
        when(runtimeTaskMapper.findById(TASK_ID)).thenReturn(managed);

        assertLeaseFails(ModelErrorCode.LEASE_NOT_BYOK);
        verify(credentialMapper, never()).findActiveById(any(), any());
    }

    @Test
    void lease_shouldRejectByokTaskWithoutCredentialReference() {
        when(runtimeTaskMapper.findById(TASK_ID)).thenReturn(byokTask(null));

        assertLeaseFails(ModelErrorCode.CREDENTIAL_REVOKED);
        verify(credentialMapper, never()).findActiveById(any(), any());
    }

    @Test
    void lease_shouldRejectRevokedOrForeignCredential() {
        when(runtimeTaskMapper.findById(TASK_ID)).thenReturn(byokTask(CREDENTIAL_ID));
        // SQL 已按 (id, user_public_id) 过滤，凭证被撤销或属于他人时都查不到
        when(credentialMapper.findActiveById(CREDENTIAL_ID, USER_ID)).thenReturn(null);

        assertLeaseFails(ModelErrorCode.CREDENTIAL_REVOKED);
        verify(runtimeTaskMapper, never()).markLeased(any(), any());
    }

    @Test
    void lease_shouldRejectSecondLease_whenConditionalUpdateMisses() {
        when(runtimeTaskMapper.findById(TASK_ID)).thenReturn(byokTask(CREDENTIAL_ID));
        when(credentialMapper.findActiveById(CREDENTIAL_ID, USER_ID)).thenReturn(credential(SECRET));
        when(runtimeTaskMapper.markLeased(TASK_ID, NOW_OFFSET)).thenReturn(0);

        assertLeaseFails(ModelErrorCode.CREDENTIAL_LEASE_CONSUMED);
    }

    @Test
    void lease_shouldNotConsumeTask_whenCiphertextIsCorrupted() {
        when(runtimeTaskMapper.findById(TASK_ID)).thenReturn(byokTask(CREDENTIAL_ID));
        when(credentialMapper.findActiveById(CREDENTIAL_ID, USER_ID)).thenReturn(corruptedCredential());

        assertLeaseFails(ModelErrorCode.CREDENTIAL_CORRUPTED);
        verify(runtimeTaskMapper, never()).markLeased(any(), any());
    }

    @Test
    void lease_shouldReturnNotFound_whenRuntimeIsDisabled() {
        properties.setRuntimeEnabled(false);

        assertLeaseFails(ModelErrorCode.RUNTIME_DISABLED);
        verifyNoInteractions(runtimeTaskMapper, credentialMapper);
    }

    private void assertLeaseFails(ModelErrorCode expected) {
        assertThatThrownBy(() -> service.lease(TASK_ID))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(expected));
    }

    private static RuntimeTaskRow byokTask(UUID credentialId) {
        return new RuntimeTaskRow(
                TASK_ID, USER_ID, "t-1", null, "openai:gpt-4o-mini", "BYOK", credentialId,
                "https://byok.example.com/v1", "ACTIVE", EXPIRES_AT, NOW_OFFSET, null);
    }

    private ProviderCredentialRow credential(String plaintext) {
        return new ProviderCredentialRow(
                CREDENTIAL_ID, CONNECTION_ID, USER_ID, "api_key", cipher.encrypt(plaintext), 1,
                "sk-****7890", "UNVERIFIED", NOW_OFFSET, null);
    }

    private static ProviderCredentialRow corruptedCredential() {
        return new ProviderCredentialRow(
                CREDENTIAL_ID, CONNECTION_ID, USER_ID, "api_key", "v1:1:AAAA", 1,
                "sk-****7890", "UNVERIFIED", NOW_OFFSET, null);
    }
}
