package com.example.agent.model;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.example.agent.identity.application.AuthAuditRecorder;
import com.example.agent.identity.domain.AuthAuditEvent;
import com.example.agent.model.application.CredentialKeyRing;
import com.example.agent.model.application.CredentialVerificationService;
import com.example.agent.model.application.ModelCredentialVerifyRateLimiter;
import com.example.agent.model.application.ModelRuntimeGuard;
import com.example.agent.model.application.ProviderConnectionService;
import com.example.agent.model.application.ProviderCredentialCipher;
import com.example.agent.model.domain.CredentialMasker;
import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.model.domain.ProviderConnectionView;
import com.example.agent.model.infrastructure.GatewayCredentialProbe;
import com.example.agent.model.infrastructure.HostResolver;
import com.example.agent.model.infrastructure.ModelCatalogMapper;
import com.example.agent.model.infrastructure.OutboundHostGuard;
import com.example.agent.model.infrastructure.ProviderCatalogStore;
import com.example.agent.model.infrastructure.ProviderConnectionMapper;
import com.example.agent.model.infrastructure.ProviderConnectionStore;
import com.example.agent.model.infrastructure.ProviderConnectionRow;
import com.example.agent.model.infrastructure.ProviderConnectionViewRow;
import com.example.agent.model.infrastructure.ProviderCredentialMapper;
import com.example.agent.model.infrastructure.ProviderCredentialRow;
import com.example.agent.model.infrastructure.ProviderRow;
import com.example.agent.shared.api.PageQuery;
import com.example.agent.shared.api.PageResult;
import com.example.agent.shared.config.ModelRuntimeProperties;
import com.example.agent.shared.error.BusinessException;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * BYOK 连接服务单测：加密、掩码、归属与删除语义都不启容器。
 *
 * <p>加解密使用真实 {@link ProviderCredentialCipher}，验证的是「入库密文不是明文、
 * 掩码与明文一致」这条完整链路，而不是对 cipher 的调用次数做断言。</p>
 */
@ExtendWith(MockitoExtension.class)
class ProviderConnectionServiceTests {

    private static final Instant NOW = Instant.parse("2026-10-30T08:00:00Z");

    private static final Clock CLOCK = Clock.fixed(NOW, ZoneOffset.UTC);

    private static final UUID USER_ID = UUID.fromString("6f5a0b36-64c6-4f38-8a9d-53e1a2c9a742");

    private static final UUID CONNECTION_ID = UUID.fromString("2a1f6b0e-5d3c-4b8a-9e7f-1c2d3e4f5a6b");

    private static final UUID CREDENTIAL_ID = UUID.fromString("8c7d6e5f-4a3b-2c1d-9e8f-7a6b5c4d3e2f");

    private static final String SECRET = "sk-test-1234567890";

    private static final String ROTATED_SECRET = "sk-rotated-abcdef123456";

    private static final String PROVIDER_CODE = "openai";

    private static final String DEFAULT_BASE_URL = "https://api.openai.com/v1";

    private static final String MASTER_KEY = java.util.Base64.getEncoder()
            .encodeToString("0123456789abcdef0123456789abcdef".getBytes(StandardCharsets.UTF_8));

    private static final ProviderRow OPENAI =
            new ProviderRow(PROVIDER_CODE, "OpenAI", "openai-compatible", DEFAULT_BASE_URL);

    @Mock
    private ModelCatalogMapper modelCatalogMapper;

    @Mock
    private ProviderConnectionMapper connectionMapper;

    @Mock
    private ProviderCredentialMapper credentialMapper;

    @Mock
    private GatewayCredentialProbe probe;

    @Mock
    private ModelCredentialVerifyRateLimiter verifyRateLimiter;

    @Mock
    private AuthAuditRecorder auditRecorder;

    @Mock
    private PlatformTransactionManager transactionManager;

    private ModelRuntimeProperties properties;

    private ProviderCredentialCipher cipher;

    private ProviderConnectionService service;

    @BeforeEach
    void setUp() {
        properties = new ModelRuntimeProperties();
        properties.setRuntimeEnabled(true);
        properties.setByokEnabled(true);
        properties.getCredential().setMasterKey(MASTER_KEY);
        properties.getCredential().setKeyVersion(1);
        cipher = new ProviderCredentialCipher(new CredentialKeyRing(properties));
        // 域名统一解析到公网地址：单测不依赖真实 DNS，也不会真的出站
        HostResolver publicResolver = host -> List.of(InetAddress.getByName("8.8.8.8"));
        // 用真实 Store 包住被 mock 的 mapper：既有桩与断言继续针对底层调用，Store 只负责映射
        ProviderConnectionStore connectionStore = new ProviderConnectionStore(connectionMapper, credentialMapper);
        ProviderCatalogStore catalogStore = new ProviderCatalogStore(modelCatalogMapper);
        CredentialVerificationService verificationService = new CredentialVerificationService(
                connectionStore, cipher, probe, auditRecorder, CLOCK,
                new TransactionTemplate(transactionManager));
        service = new ProviderConnectionService(
                new ModelRuntimeGuard(properties), catalogStore, connectionStore,
                cipher, new OutboundHostGuard(publicResolver), verifyRateLimiter, auditRecorder,
                verificationService, properties, CLOCK, new TransactionTemplate(transactionManager));
    }

    @Test
    void create_shouldEncryptSecretAndReturnOnlyMaskedCredential() {
        when(modelCatalogMapper.findEnabledProvider(PROVIDER_CODE)).thenReturn(OPENAI);
        when(connectionMapper.insert(any(ProviderConnectionRow.class))).thenReturn(1);
        when(credentialMapper.insert(any(ProviderCredentialRow.class))).thenReturn(1);
        when(connectionMapper.findActiveViewById(any(UUID.class), eq(USER_ID))).thenReturn(viewRow(
                CONNECTION_ID, CREDENTIAL_ID, CredentialMasker.mask(SECRET), ""));

        ProviderConnectionView view = service.create(USER_ID, " openai ", null, "  " + SECRET + "  ");

        assertThat(view.provider()).isEqualTo(PROVIDER_CODE);
        // 未填地址就原样存空，由网关使用 Provider 官方默认地址
        assertThat(view.baseUrl()).isEmpty();
        assertThat(view.credential().maskedHint()).isEqualTo(CredentialMasker.mask(SECRET));

        ArgumentCaptor<ProviderConnectionRow> connectionCaptor = ArgumentCaptor.forClass(ProviderConnectionRow.class);
        verify(connectionMapper).insert(connectionCaptor.capture());
        assertThat(connectionCaptor.getValue().baseUrl()).isEmpty();

        ArgumentCaptor<ProviderCredentialRow> captor = ArgumentCaptor.forClass(ProviderCredentialRow.class);
        verify(credentialMapper).insert(captor.capture());
        ProviderCredentialRow stored = captor.getValue();
        assertThat(stored.ciphertext()).startsWith("v1:1:").doesNotContain(SECRET);
        assertThat(stored.maskedHint()).isEqualTo(CredentialMasker.mask(SECRET));
        assertThat(stored.status()).isEqualTo("UNVERIFIED");
        assertThat(stored.keyVersion()).isEqualTo(1);
    }

    @Test
    void create_shouldAutoVerify_whenProviderAcceptsCredential() {
        when(modelCatalogMapper.findEnabledProvider(PROVIDER_CODE)).thenReturn(OPENAI);
        when(connectionMapper.insert(any(ProviderConnectionRow.class))).thenReturn(1);
        when(credentialMapper.insert(any(ProviderCredentialRow.class))).thenReturn(1);
        when(probe.probe(PROVIDER_CODE, "", SECRET))
                .thenReturn(GatewayCredentialProbe.Outcome.VERIFIED);
        when(credentialMapper.findActiveByConnection(any(UUID.class), eq(USER_ID)))
                .thenReturn(credential(cipher.encrypt(SECRET), CredentialMasker.mask(SECRET)));
        when(connectionMapper.findActiveViewById(any(UUID.class), eq(USER_ID)))
                .thenReturn(viewRow(CONNECTION_ID, CREDENTIAL_ID, CredentialMasker.mask(SECRET),
                        "", "VERIFIED", OffsetDateTime.now(CLOCK)));
        when(connectionMapper.markVerified(any(UUID.class), eq(USER_ID), any(OffsetDateTime.class)))
                .thenReturn(1);
        when(credentialMapper.markVerified(any(UUID.class), eq(USER_ID))).thenReturn(1);

        ProviderConnectionView view = service.create(USER_ID, PROVIDER_CODE, null, SECRET);

        // 创建即验证：不需要用户再手动点一次
        assertThat(view.credential().status()).isEqualTo("VERIFIED");
        verify(credentialMapper).markVerified(any(UUID.class), eq(USER_ID));
        verify(auditRecorder).recordForUser(AuthAuditEvent.MODEL_CREDENTIAL_CREATED, USER_ID);
        verify(auditRecorder).recordForUser(AuthAuditEvent.MODEL_CREDENTIAL_VERIFIED, USER_ID);
    }

    @Test
    void create_shouldKeepConnection_whenAutoVerifyRejects() {
        when(modelCatalogMapper.findEnabledProvider(PROVIDER_CODE)).thenReturn(OPENAI);
        when(connectionMapper.insert(any(ProviderConnectionRow.class))).thenReturn(1);
        when(credentialMapper.insert(any(ProviderCredentialRow.class))).thenReturn(1);
        when(probe.probe(PROVIDER_CODE, "", SECRET))
                .thenReturn(GatewayCredentialProbe.Outcome.REJECTED);
        when(credentialMapper.findActiveByConnection(any(UUID.class), eq(USER_ID)))
                .thenReturn(credential(cipher.encrypt(SECRET), CredentialMasker.mask(SECRET)));
        when(connectionMapper.findActiveViewById(any(UUID.class), eq(USER_ID)))
                .thenReturn(viewRow(CONNECTION_ID, CREDENTIAL_ID, CredentialMasker.mask(SECRET), ""));

        ProviderConnectionView view = service.create(USER_ID, PROVIDER_CODE, null, SECRET);

        // 自动验证失败不回滚连接，只把状态留在 UNVERIFIED 供用户修正密钥
        assertThat(view.credential().status()).isEqualTo("UNVERIFIED");
        verify(connectionMapper, never()).markVerified(any(), any(), any());
        verify(credentialMapper, never()).markVerified(any(), any());
        verify(auditRecorder).recordForUser(AuthAuditEvent.MODEL_CREDENTIAL_VERIFY_FAILED, USER_ID);
    }

    @Test
    void create_shouldTrimTrailingSlashFromCustomBaseUrl() {
        when(modelCatalogMapper.findEnabledProvider(PROVIDER_CODE)).thenReturn(OPENAI);
        when(connectionMapper.insert(any(ProviderConnectionRow.class))).thenReturn(1);
        when(credentialMapper.insert(any(ProviderCredentialRow.class))).thenReturn(1);
        when(connectionMapper.findActiveViewById(any(UUID.class), eq(USER_ID)))
                .thenReturn(viewRow(CONNECTION_ID, CREDENTIAL_ID, CredentialMasker.mask(SECRET), "https://proxy.example.com/v1"));

        service.create(USER_ID, PROVIDER_CODE, "https://proxy.example.com/v1/", SECRET);

        ArgumentCaptor<ProviderConnectionRow> captor = ArgumentCaptor.forClass(ProviderConnectionRow.class);
        verify(connectionMapper).insert(captor.capture());
        assertThat(captor.getValue().baseUrl()).isEqualTo("https://proxy.example.com/v1");
    }

    @Test
    void create_shouldRejectDuplicateProviderConnection() {
        when(modelCatalogMapper.findEnabledProvider(PROVIDER_CODE)).thenReturn(OPENAI);
        when(connectionMapper.insert(any(ProviderConnectionRow.class)))
                .thenThrow(new DuplicateKeyException("uk_provider_connections_user_provider_active"));

        assertThatThrownBy(() -> service.create(USER_ID, PROVIDER_CODE, null, SECRET))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.CONNECTION_EXISTS));
        // 连接插入失败时不能留下孤立凭证
        verify(credentialMapper, never()).insert(any(ProviderCredentialRow.class));
    }

    @Test
    void create_shouldRejectUnknownProvider() {
        when(modelCatalogMapper.findEnabledProvider("unknown")).thenReturn(null);

        assertThatThrownBy(() -> service.create(USER_ID, "unknown", null, SECRET))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.PROVIDER_NOT_SUPPORTED));
        verifyNoInteractions(connectionMapper, credentialMapper);
    }

    @Test
    void create_shouldRejectInvalidExplicitBaseUrl() {
        when(modelCatalogMapper.findEnabledProvider("no-default"))
                .thenReturn(new ProviderRow("no-default", "NoDefault", "openai-compatible", null));

        // 未填地址合法（交给网关），只有显式填写的非法地址才拒绝
        assertThatThrownBy(() -> service.create(USER_ID, "no-default", "ftp://example.com", SECRET))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.BASE_URL_INVALID));
        assertThatThrownBy(() -> service.create(USER_ID, "no-default", "https://", SECRET))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.BASE_URL_INVALID));
        verifyNoInteractions(connectionMapper, credentialMapper);
    }

    @Test
    void create_shouldRejectLoopbackAndPrivateBaseUrl() {
        when(modelCatalogMapper.findEnabledProvider("no-default"))
                .thenReturn(new ProviderRow("no-default", "NoDefault", "openai-compatible", null));

        String[] forbiddenUrls = {
                "http://localhost:11434/v1", "http://127.0.0.1/v1", "http://[::1]/v1",
                "http://10.0.0.5/v1", "http://192.168.1.10/v1"};
        for (String url : forbiddenUrls) {
            assertThatThrownBy(() -> service.create(USER_ID, "no-default", url, SECRET))
                    .isInstanceOfSatisfying(BusinessException.class,
                            ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.BASE_URL_INVALID));
        }
        verifyNoInteractions(connectionMapper, credentialMapper);
    }

    @Test
    void list_shouldMapConnectionViews() {
        when(connectionMapper.findActiveViewsByUser(USER_ID))
                .thenReturn(List.of(viewRow(CONNECTION_ID, CREDENTIAL_ID, CredentialMasker.mask(SECRET))));

        List<ProviderConnectionView> connections = service.list(USER_ID);

        assertThat(connections).singleElement().satisfies(view -> {
            assertThat(view.id()).isEqualTo(CONNECTION_ID);
            assertThat(view.provider()).isEqualTo(PROVIDER_CODE);
            assertThat(view.credential().maskedHint()).isEqualTo(CredentialMasker.mask(SECRET));
        });
    }

    @Test
    void listPage_shouldReturnRequestedSliceAndTotal() {
        when(connectionMapper.countActiveByUser(USER_ID)).thenReturn(1L);
        when(connectionMapper.findActiveViewsPageByUser(USER_ID, 0L, 2))
                .thenReturn(List.of(viewRow(CONNECTION_ID, CREDENTIAL_ID, CredentialMasker.mask(SECRET))));
        PageQuery query = new PageQuery();
        query.setSize(2);

        PageResult<ProviderConnectionView> page = service.list(USER_ID, query);

        assertThat(page.total()).isEqualTo(1);
        assertThat(page.page()).isEqualTo(1);
        assertThat(page.size()).isEqualTo(2);
        assertThat(page.list()).singleElement()
                .satisfies(view -> assertThat(view.id()).isEqualTo(CONNECTION_ID));
    }

    @Test
    void listPage_shouldReturnEmptyPage_whenOffsetBeyondTotal() {
        when(connectionMapper.countActiveByUser(USER_ID)).thenReturn(1L);
        PageQuery query = new PageQuery();
        query.setPage(3);
        query.setSize(2);

        PageResult<ProviderConnectionView> page = service.list(USER_ID, query);

        assertThat(page.list()).isEmpty();
        assertThat(page.total()).isEqualTo(1);
        verify(connectionMapper, never()).findActiveViewsPageByUser(USER_ID, 4L, 2);
    }

    @Test
    void verify_shouldMarkVerified_whenProviderAcceptsCredential() {
        OffsetDateTime verifiedAt = OffsetDateTime.now(CLOCK);
        when(connectionMapper.findActiveViewById(CONNECTION_ID, USER_ID))
                .thenReturn(viewRow(CONNECTION_ID, CREDENTIAL_ID, CredentialMasker.mask(SECRET)),
                        viewRow(CONNECTION_ID, CREDENTIAL_ID, CredentialMasker.mask(SECRET),
                                DEFAULT_BASE_URL, "VERIFIED", verifiedAt));
        when(credentialMapper.findActiveByConnection(CONNECTION_ID, USER_ID))
                .thenReturn(credential(cipher.encrypt(SECRET), CredentialMasker.mask(SECRET)));
        when(probe.probe(PROVIDER_CODE, DEFAULT_BASE_URL, SECRET))
                .thenReturn(GatewayCredentialProbe.Outcome.VERIFIED);

        ProviderConnectionView view = service.verify(USER_ID, CONNECTION_ID);

        assertThat(view.credential().status()).isEqualTo("VERIFIED");
        assertThat(view.lastVerifiedAt()).isEqualTo(verifiedAt);
        verify(connectionMapper).markVerified(CONNECTION_ID, USER_ID, verifiedAt);
        verify(credentialMapper).markVerified(CREDENTIAL_ID, USER_ID);
    }

    @Test
    void verify_shouldFail_whenProviderRejectsCredential() {
        when(connectionMapper.findActiveViewById(CONNECTION_ID, USER_ID))
                .thenReturn(viewRow(CONNECTION_ID, CREDENTIAL_ID, CredentialMasker.mask(SECRET)));
        when(credentialMapper.findActiveByConnection(CONNECTION_ID, USER_ID))
                .thenReturn(credential(cipher.encrypt(SECRET), CredentialMasker.mask(SECRET)));
        when(probe.probe(PROVIDER_CODE, DEFAULT_BASE_URL, SECRET))
                .thenReturn(GatewayCredentialProbe.Outcome.REJECTED);

        assertThatThrownBy(() -> service.verify(USER_ID, CONNECTION_ID))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.CREDENTIAL_REJECTED));
        verify(connectionMapper, never()).markVerified(any(), any(), any());
        verify(credentialMapper, never()).markVerified(any(), any());
    }

    @Test
    void verify_shouldFail_whenProviderIsUnavailable() {
        when(connectionMapper.findActiveViewById(CONNECTION_ID, USER_ID))
                .thenReturn(viewRow(CONNECTION_ID, CREDENTIAL_ID, CredentialMasker.mask(SECRET)));
        when(credentialMapper.findActiveByConnection(CONNECTION_ID, USER_ID))
                .thenReturn(credential(cipher.encrypt(SECRET), CredentialMasker.mask(SECRET)));
        when(probe.probe(PROVIDER_CODE, DEFAULT_BASE_URL, SECRET))
                .thenReturn(GatewayCredentialProbe.Outcome.UNAVAILABLE);

        assertThatThrownBy(() -> service.verify(USER_ID, CONNECTION_ID))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.CREDENTIAL_VERIFY_FAILED));
        verify(connectionMapper, never()).markVerified(any(), any(), any());
    }

    @Test
    void verify_shouldFail_whenCredentialIsMissing() {
        when(connectionMapper.findActiveViewById(CONNECTION_ID, USER_ID))
                .thenReturn(viewRow(CONNECTION_ID, null, null));
        when(credentialMapper.findActiveByConnection(CONNECTION_ID, USER_ID)).thenReturn(null);

        assertThatThrownBy(() -> service.verify(USER_ID, CONNECTION_ID))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.CONNECTION_NOT_FOUND));
    }

    @Test
    void verify_shouldFail_whenCiphertextIsCorrupted() {
        when(connectionMapper.findActiveViewById(CONNECTION_ID, USER_ID))
                .thenReturn(viewRow(CONNECTION_ID, CREDENTIAL_ID, CredentialMasker.mask(SECRET)));
        when(credentialMapper.findActiveByConnection(CONNECTION_ID, USER_ID))
                .thenReturn(credential("v1:1:AAAA", CredentialMasker.mask(SECRET)));

        assertThatThrownBy(() -> service.verify(USER_ID, CONNECTION_ID))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.CREDENTIAL_CORRUPTED));
    }

    @Test
    void verify_shouldFail_whenMaskDoesNotMatchPlaintext() {
        when(connectionMapper.findActiveViewById(CONNECTION_ID, USER_ID))
                .thenReturn(viewRow(CONNECTION_ID, CREDENTIAL_ID, "sk-****0000"));
        when(credentialMapper.findActiveByConnection(CONNECTION_ID, USER_ID))
                .thenReturn(credential(cipher.encrypt(SECRET), "sk-****0000"));

        assertThatThrownBy(() -> service.verify(USER_ID, CONNECTION_ID))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.CREDENTIAL_CORRUPTED));
    }

    @Test
    void update_shouldRotateCredentialAndAutoVerify() {
        when(connectionMapper.findActiveViewById(CONNECTION_ID, USER_ID))
                .thenReturn(viewRow(CONNECTION_ID, CREDENTIAL_ID, CredentialMasker.mask(SECRET)),
                        viewRow(CONNECTION_ID, CREDENTIAL_ID, CredentialMasker.mask(ROTATED_SECRET),
                                DEFAULT_BASE_URL, "VERIFIED", OffsetDateTime.now(CLOCK)));
        when(modelCatalogMapper.findEnabledProvider(PROVIDER_CODE)).thenReturn(OPENAI);
        when(connectionMapper.updateBaseUrl(
                eq(CONNECTION_ID), eq(USER_ID), eq(DEFAULT_BASE_URL), any(OffsetDateTime.class))).thenReturn(1);
        when(credentialMapper.markRevokedByConnection(
                eq(CONNECTION_ID), eq(USER_ID), any(OffsetDateTime.class))).thenReturn(1);
        when(credentialMapper.insert(any(ProviderCredentialRow.class))).thenReturn(1);
        when(probe.probe(PROVIDER_CODE, DEFAULT_BASE_URL, ROTATED_SECRET))
                .thenReturn(GatewayCredentialProbe.Outcome.VERIFIED);
        when(credentialMapper.findActiveByConnection(any(UUID.class), eq(USER_ID)))
                .thenReturn(credential(cipher.encrypt(ROTATED_SECRET), CredentialMasker.mask(ROTATED_SECRET)));
        when(connectionMapper.markVerified(eq(CONNECTION_ID), eq(USER_ID), any(OffsetDateTime.class)))
                .thenReturn(1);
        when(credentialMapper.markVerified(any(UUID.class), eq(USER_ID))).thenReturn(1);

        ProviderConnectionView view = service.update(USER_ID, CONNECTION_ID, null, ROTATED_SECRET);

        // 轮换语义：旧凭证先撤销，再写入新凭证并自动验证
        assertThat(view.credential().status()).isEqualTo("VERIFIED");
        verify(credentialMapper).markRevokedByConnection(
                eq(CONNECTION_ID), eq(USER_ID), eq(OffsetDateTime.now(CLOCK)));
        ArgumentCaptor<ProviderCredentialRow> captor = ArgumentCaptor.forClass(ProviderCredentialRow.class);
        verify(credentialMapper).insert(captor.capture());
        assertThat(captor.getValue().maskedHint()).isEqualTo(CredentialMasker.mask(ROTATED_SECRET));
        assertThat(captor.getValue().ciphertext()).startsWith("v1:1:").doesNotContain(ROTATED_SECRET);
        verify(auditRecorder).recordForUser(AuthAuditEvent.MODEL_CREDENTIAL_UPDATED, USER_ID);
    }

    @Test
    void update_shouldReturnNotFound_whenConnectionIsAbsent() {
        when(connectionMapper.findActiveViewById(CONNECTION_ID, USER_ID)).thenReturn(null);

        assertThatThrownBy(() -> service.update(USER_ID, CONNECTION_ID, null, ROTATED_SECRET))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.CONNECTION_NOT_FOUND));
        verify(credentialMapper, never()).insert(any(ProviderCredentialRow.class));
    }

    @Test
    void verify_shouldRateLimitBeforeTouchingCredentials() {
        doThrow(new BusinessException(ModelErrorCode.CREDENTIAL_VERIFY_RATE_LIMITED))
                .when(verifyRateLimiter).requireAllowed(USER_ID);

        assertThatThrownBy(() -> service.verify(USER_ID, CONNECTION_ID))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode())
                                .isEqualTo(ModelErrorCode.CREDENTIAL_VERIFY_RATE_LIMITED));
        // 限流必须在解密与出站之前生效，避免被当作探测入口
        verifyNoInteractions(connectionMapper, credentialMapper);
    }

    @Test
    void delete_shouldSoftDeleteConnectionAndRevokeCredential() {
        when(connectionMapper.findActiveViewById(CONNECTION_ID, USER_ID))
                .thenReturn(viewRow(CONNECTION_ID, CREDENTIAL_ID, CredentialMasker.mask(SECRET)));
        when(connectionMapper.markDeleted(eq(CONNECTION_ID), eq(USER_ID), any(OffsetDateTime.class))).thenReturn(1);

        service.delete(USER_ID, CONNECTION_ID);

        verify(connectionMapper).markDeleted(eq(CONNECTION_ID), eq(USER_ID), eq(OffsetDateTime.now(CLOCK)));
        verify(credentialMapper).markRevokedByConnection(eq(CONNECTION_ID), eq(USER_ID), eq(OffsetDateTime.now(CLOCK)));
    }

    @Test
    void delete_shouldReturnNotFound_whenConnectionIsAbsent() {
        when(connectionMapper.findActiveViewById(CONNECTION_ID, USER_ID)).thenReturn(null);

        assertThatThrownBy(() -> service.delete(USER_ID, CONNECTION_ID))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.CONNECTION_NOT_FOUND));
        verify(connectionMapper, never()).markDeleted(any(), any(), any());
        verify(credentialMapper, never()).markRevokedByConnection(any(), any(), any());
    }

    @Test
    void delete_shouldNotRevokeCredential_whenConnectionWasAlreadyDeletedConcurrently() {
        when(connectionMapper.findActiveViewById(CONNECTION_ID, USER_ID))
                .thenReturn(viewRow(CONNECTION_ID, CREDENTIAL_ID, CredentialMasker.mask(SECRET)));
        when(connectionMapper.markDeleted(eq(CONNECTION_ID), eq(USER_ID), any(OffsetDateTime.class))).thenReturn(0);

        assertThatThrownBy(() -> service.delete(USER_ID, CONNECTION_ID))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.CONNECTION_NOT_FOUND));
        verify(credentialMapper, never()).markRevokedByConnection(any(), any(), any());
    }

    @Test
    void allOperations_shouldReturnByokDisabled_whenSwitchIsOff() {
        properties.setByokEnabled(false);

        assertThatThrownBy(() -> service.list(USER_ID))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.BYOK_DISABLED));
        assertThatThrownBy(() -> service.list(USER_ID, new PageQuery()))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.BYOK_DISABLED));
        assertThatThrownBy(() -> service.create(USER_ID, PROVIDER_CODE, null, SECRET))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.BYOK_DISABLED));
        assertThatThrownBy(() -> service.verify(USER_ID, CONNECTION_ID))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.BYOK_DISABLED));
        assertThatThrownBy(() -> service.delete(USER_ID, CONNECTION_ID))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.BYOK_DISABLED));
        verifyNoInteractions(modelCatalogMapper, connectionMapper, credentialMapper);
    }

    private static ProviderConnectionViewRow viewRow(UUID connectionId, UUID credentialId, String maskedHint) {
        return viewRow(connectionId, credentialId, maskedHint, DEFAULT_BASE_URL);
    }

    private static ProviderConnectionViewRow viewRow(
            UUID connectionId, UUID credentialId, String maskedHint, String baseUrl) {
        return viewRow(connectionId, credentialId, maskedHint, baseUrl, "UNVERIFIED", null);
    }

    private static ProviderConnectionViewRow viewRow(
            UUID connectionId, UUID credentialId, String maskedHint, String baseUrl,
            String credentialStatus, OffsetDateTime lastVerifiedAt) {
        OffsetDateTime createdAt = OffsetDateTime.parse("2026-10-30T08:00:00Z");
        return new ProviderConnectionViewRow(
                connectionId, PROVIDER_CODE, "OpenAI", baseUrl, "ACTIVE", lastVerifiedAt, createdAt,
                credentialId, maskedHint, credentialId == null ? null : credentialStatus,
                credentialId == null ? null : createdAt);
    }

    private static ProviderCredentialRow credential(String ciphertext, String maskedHint) {
        return new ProviderCredentialRow(
                CREDENTIAL_ID, CONNECTION_ID, USER_ID, "api_key", ciphertext, 1, maskedHint,
                "UNVERIFIED", OffsetDateTime.parse("2026-10-30T08:00:00Z"), null);
    }
}
