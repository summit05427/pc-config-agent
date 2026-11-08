package com.example.agent.model;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.example.agent.identity.application.AuthAuditRecorder;
import com.example.agent.identity.domain.AuthAuditEvent;
import com.example.agent.model.application.CredentialKeyRing;
import com.example.agent.model.application.CredentialVerificationService;
import com.example.agent.model.application.ProviderCredentialCipher;
import com.example.agent.model.domain.CredentialMasker;
import com.example.agent.model.domain.CredentialVerificationOutcome;
import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.model.infrastructure.GatewayCredentialProbe;
import com.example.agent.model.infrastructure.ProviderConnectionMapper;
import com.example.agent.model.infrastructure.ProviderConnectionStore;
import com.example.agent.model.infrastructure.ProviderConnectionViewRow;
import com.example.agent.model.infrastructure.ProviderCredentialMapper;
import com.example.agent.model.infrastructure.ProviderCredentialRow;
import com.example.agent.shared.config.ModelRuntimeProperties;
import com.example.agent.shared.error.BusinessException;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 凭证验证模块单测：覆盖四种结果、事务回写与审计次数，不启动容器、不出站。
 */
@ExtendWith(MockitoExtension.class)
class CredentialVerificationServiceTests {

    private static final Instant NOW = Instant.parse("2026-10-30T08:00:00Z");

    private static final Clock CLOCK = Clock.fixed(NOW, ZoneOffset.UTC);

    private static final UUID USER_ID = UUID.fromString("6f5a0b36-64c6-4f38-8a9d-53e1a2c9a742");

    private static final UUID CONNECTION_ID = UUID.fromString("2a1f6b0e-5d3c-4b8a-9e7f-1c2d3e4f5a6b");

    private static final UUID CREDENTIAL_ID = UUID.fromString("8c7d6e5f-4a3b-2c1d-9e8f-7a6b5c4d3e2f");

    private static final String SECRET = "sk-test-1234567890";

    private static final String PROVIDER_CODE = "openai";

    private static final String BASE_URL = "https://api.openai.com/v1";

    private static final String MASTER_KEY = java.util.Base64.getEncoder()
            .encodeToString("0123456789abcdef0123456789abcdef".getBytes(StandardCharsets.UTF_8));

    @Mock
    private ProviderConnectionMapper connectionMapper;

    @Mock
    private ProviderCredentialMapper credentialMapper;

    @Mock
    private GatewayCredentialProbe probe;

    @Mock
    private AuthAuditRecorder auditRecorder;

    @Mock
    private PlatformTransactionManager transactionManager;

    private ProviderCredentialCipher cipher;

    private CredentialVerificationService service;

    @BeforeEach
    void setUp() {
        ModelRuntimeProperties properties = new ModelRuntimeProperties();
        properties.getCredential().setMasterKey(MASTER_KEY);
        properties.getCredential().setKeyVersion(1);
        cipher = new ProviderCredentialCipher(new CredentialKeyRing(properties));
        // 真实 Store 包住被 mock 的 mapper，保留原有对底层调用的断言
        service = new CredentialVerificationService(
                new ProviderConnectionStore(connectionMapper, credentialMapper), cipher, probe, auditRecorder,
                CLOCK, new TransactionTemplate(transactionManager));
    }

    @Test
    void verify_shouldMarkVerifiedAndAudit_whenProviderAccepts() {
        when(connectionMapper.findActiveViewById(CONNECTION_ID, USER_ID))
                .thenReturn(viewRow(CredentialMasker.mask(SECRET)));
        when(credentialMapper.findActiveByConnection(CONNECTION_ID, USER_ID))
                .thenReturn(credential(cipher.encrypt(SECRET), CredentialMasker.mask(SECRET)));
        when(probe.probe(PROVIDER_CODE, BASE_URL, SECRET))
                .thenReturn(GatewayCredentialProbe.Outcome.VERIFIED);

        CredentialVerificationOutcome outcome = service.verify(USER_ID, CONNECTION_ID);

        assertThat(outcome).isEqualTo(CredentialVerificationOutcome.VERIFIED);
        verify(connectionMapper).markVerified(CONNECTION_ID, USER_ID, OffsetDateTime.now(CLOCK));
        verify(credentialMapper).markVerified(CREDENTIAL_ID, USER_ID);
        verify(auditRecorder).recordForUser(AuthAuditEvent.MODEL_CREDENTIAL_VERIFIED, USER_ID);
    }

    @Test
    void verify_shouldAuditFailureWithoutMarking_whenProviderRejects() {
        when(connectionMapper.findActiveViewById(CONNECTION_ID, USER_ID))
                .thenReturn(viewRow(CredentialMasker.mask(SECRET)));
        when(credentialMapper.findActiveByConnection(CONNECTION_ID, USER_ID))
                .thenReturn(credential(cipher.encrypt(SECRET), CredentialMasker.mask(SECRET)));
        when(probe.probe(PROVIDER_CODE, BASE_URL, SECRET))
                .thenReturn(GatewayCredentialProbe.Outcome.REJECTED);

        CredentialVerificationOutcome outcome = service.verify(USER_ID, CONNECTION_ID);

        assertThat(outcome).isEqualTo(CredentialVerificationOutcome.REJECTED);
        verify(connectionMapper, never()).markVerified(org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any());
        verify(auditRecorder).recordForUser(AuthAuditEvent.MODEL_CREDENTIAL_VERIFY_FAILED, USER_ID);
    }

    @Test
    void verify_shouldReturnUnavailableWithoutMarking_whenProviderIsUnreachable() {
        when(connectionMapper.findActiveViewById(CONNECTION_ID, USER_ID))
                .thenReturn(viewRow(CredentialMasker.mask(SECRET)));
        when(credentialMapper.findActiveByConnection(CONNECTION_ID, USER_ID))
                .thenReturn(credential(cipher.encrypt(SECRET), CredentialMasker.mask(SECRET)));
        when(probe.probe(PROVIDER_CODE, BASE_URL, SECRET))
                .thenReturn(GatewayCredentialProbe.Outcome.UNAVAILABLE);

        CredentialVerificationOutcome outcome = service.verify(USER_ID, CONNECTION_ID);

        assertThat(outcome).isEqualTo(CredentialVerificationOutcome.UNAVAILABLE);
        verify(credentialMapper, never()).markVerified(
                org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any());
        verify(auditRecorder).recordForUser(AuthAuditEvent.MODEL_CREDENTIAL_VERIFY_FAILED, USER_ID);
    }

    @Test
    void verify_shouldReturnCorruptedWithoutProbe_whenMaskDoesNotMatch() {
        when(connectionMapper.findActiveViewById(CONNECTION_ID, USER_ID))
                .thenReturn(viewRow("sk-****0000"));
        when(credentialMapper.findActiveByConnection(CONNECTION_ID, USER_ID))
                .thenReturn(credential(cipher.encrypt(SECRET), "sk-****0000"));

        CredentialVerificationOutcome outcome = service.verify(USER_ID, CONNECTION_ID);

        assertThat(outcome).isEqualTo(CredentialVerificationOutcome.CORRUPTED);
        verifyNoInteractions(probe);
        verify(auditRecorder).recordForUser(AuthAuditEvent.MODEL_CREDENTIAL_VERIFY_FAILED, USER_ID);
    }

    @Test
    void verify_shouldReturnCorruptedWithoutProbe_whenCiphertextIsUnreadable() {
        when(connectionMapper.findActiveViewById(CONNECTION_ID, USER_ID))
                .thenReturn(viewRow(CredentialMasker.mask(SECRET)));
        when(credentialMapper.findActiveByConnection(CONNECTION_ID, USER_ID))
                .thenReturn(credential("v1:1:AAAA", CredentialMasker.mask(SECRET)));

        CredentialVerificationOutcome outcome = service.verify(USER_ID, CONNECTION_ID);

        assertThat(outcome).isEqualTo(CredentialVerificationOutcome.CORRUPTED);
        verifyNoInteractions(probe);
        verify(auditRecorder).recordForUser(AuthAuditEvent.MODEL_CREDENTIAL_VERIFY_FAILED, USER_ID);
    }

    @Test
    void verify_shouldThrowNotFound_whenConnectionIsMissing() {
        when(connectionMapper.findActiveViewById(CONNECTION_ID, USER_ID)).thenReturn(null);

        assertThatThrownBy(() -> service.verify(USER_ID, CONNECTION_ID))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.CONNECTION_NOT_FOUND));
        verifyNoInteractions(credentialMapper, probe, auditRecorder);
    }

    @Test
    void verify_shouldThrowNotFound_whenActiveCredentialIsMissing() {
        when(connectionMapper.findActiveViewById(CONNECTION_ID, USER_ID))
                .thenReturn(viewRow(null));
        when(credentialMapper.findActiveByConnection(CONNECTION_ID, USER_ID)).thenReturn(null);

        assertThatThrownBy(() -> service.verify(USER_ID, CONNECTION_ID))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.CONNECTION_NOT_FOUND));
        verifyNoInteractions(probe, auditRecorder);
    }

    @Test
    void verify_shouldAuditAndRethrow_whenAddressIsRejected() {
        when(connectionMapper.findActiveViewById(CONNECTION_ID, USER_ID))
                .thenReturn(viewRow(CredentialMasker.mask(SECRET)));
        when(credentialMapper.findActiveByConnection(CONNECTION_ID, USER_ID))
                .thenReturn(credential(cipher.encrypt(SECRET), CredentialMasker.mask(SECRET)));
        when(probe.probe(PROVIDER_CODE, BASE_URL, SECRET))
                .thenThrow(new BusinessException(ModelErrorCode.BASE_URL_INVALID));

        assertThatThrownBy(() -> service.verify(USER_ID, CONNECTION_ID))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.BASE_URL_INVALID));
        verify(connectionMapper, never()).markVerified(org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any());
        verify(auditRecorder).recordForUser(AuthAuditEvent.MODEL_CREDENTIAL_VERIFY_FAILED, USER_ID);
    }

    private static ProviderConnectionViewRow viewRow(String maskedHint) {
        OffsetDateTime createdAt = OffsetDateTime.parse("2026-10-30T08:00:00Z");
        UUID credentialId = maskedHint == null ? null : CREDENTIAL_ID;
        return new ProviderConnectionViewRow(
                CONNECTION_ID, PROVIDER_CODE, "OpenAI", BASE_URL, "ACTIVE", null, createdAt,
                credentialId, maskedHint, credentialId == null ? null : "UNVERIFIED",
                credentialId == null ? null : createdAt);
    }

    private static ProviderCredentialRow credential(String ciphertext, String maskedHint) {
        return new ProviderCredentialRow(
                CREDENTIAL_ID, CONNECTION_ID, USER_ID, "api_key", ciphertext, 1, maskedHint,
                "UNVERIFIED", OffsetDateTime.parse("2026-10-30T08:00:00Z"), null);
    }
}
