package com.example.agent.model;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.agent.model.application.ModelCatalogService;
import com.example.agent.model.application.ModelRuntimeGuard;
import com.example.agent.model.application.ModelRuntimeService;
import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.model.domain.ModelTaskView;
import com.example.agent.model.domain.QuotaExceededDetail;
import com.example.agent.model.domain.ResolvedModel;
import com.example.agent.model.infrastructure.ProviderConnectionMapper;
import com.example.agent.model.infrastructure.ProviderConnectionStore;
import com.example.agent.model.infrastructure.ProviderConnectionViewRow;
import com.example.agent.model.infrastructure.ProviderCredentialMapper;
import com.example.agent.model.infrastructure.QuotaMapper;
import com.example.agent.model.infrastructure.QuotaRow;
import com.example.agent.model.infrastructure.QuotaStore;
import com.example.agent.model.infrastructure.RuntimeTaskMapper;
import com.example.agent.model.infrastructure.RuntimeTaskRow;
import com.example.agent.model.infrastructure.RuntimeTaskStore;
import com.example.agent.shared.config.ModelRuntimeProperties;
import com.example.agent.shared.error.BusinessException;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
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

/**
 * 运行时任务服务单测：额度扣减、模型解析失败与归属校验都不启容器。
 */
@ExtendWith(MockitoExtension.class)
class ModelRuntimeServiceTests {

    private static final Instant NOW = Instant.parse("2026-10-30T08:00:00Z");

    private static final UUID USER_ID = UUID.fromString("6f5a0b36-64c6-4f38-8a9d-53e1a2c9a742");

    private static final UUID TASK_ID = UUID.fromString("9d2a6b4a-1c58-4d9a-9a54-2f6a8c1f0b21");

    private static final UUID CREDENTIAL_ID = UUID.fromString("8c7d6e5f-4a3b-2c1d-9e8f-7a6b5c4d3e2f");

    private static final String BYOK_BASE_URL = "https://byok.example.com/v1";

    @Mock
    private ModelCatalogService modelCatalogService;

    @Mock
    private QuotaMapper quotaMapper;

    @Mock
    private RuntimeTaskMapper runtimeTaskMapper;

    @Mock
    private ProviderConnectionMapper connectionMapper;

    @Mock
    private ProviderCredentialMapper credentialMapper;

    private ModelRuntimeProperties properties;

    private ModelRuntimeService service;

    @BeforeEach
    void setUp() {
        properties = new ModelRuntimeProperties();
        properties.setRuntimeEnabled(true);
        properties.getQuota().setDailyRequests(2);
        properties.setTaskTtl(Duration.ofMinutes(10));
        Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
        // 真实 Store 包住被 mock 的 mapper，保留原有对底层调用的断言
        service = new ModelRuntimeService(
                modelCatalogService, new ModelRuntimeGuard(properties),
                new QuotaStore(quotaMapper), new RuntimeTaskStore(runtimeTaskMapper),
                new ProviderConnectionStore(connectionMapper, credentialMapper), properties, clock);
    }

    @Test
    void createTask_shouldConsumeQuotaAndPersistManagedTask() {
        ResolvedModel model = new ResolvedModel("openai", "gpt-4o-mini", "GPT-4o mini",
                List.of("text", "reasoning", "reasoning_visible"), 128000);
        when(modelCatalogService.requireAvailable("openai:gpt-4o-mini", USER_ID)).thenReturn(model);
        when(quotaMapper.tryConsume(USER_ID, LocalDate.of(2026, 10, 30), 2)).thenReturn(new QuotaRow(1, 2));
        when(runtimeTaskMapper.insert(any(RuntimeTaskRow.class))).thenReturn(1);

        ModelTaskView view = service.createTask(USER_ID, "t-1", "openai:gpt-4o-mini", null);

        assertThat(view.provider()).isEqualTo("openai");
        assertThat(view.modelKey()).isEqualTo("openai:gpt-4o-mini");
        assertThat(view.credentialSource()).isEqualTo("MANAGED");
        assertThat(view.expiresAt()).isEqualTo(OffsetDateTime.parse("2026-10-30T08:10:00Z"));
        // Agent 靠这个字段做请求侧门控：目录能力必须原样带到任务视图
        assertThat(view.capabilities()).containsExactly("text", "reasoning", "reasoning_visible");

        ArgumentCaptor<RuntimeTaskRow> captor = ArgumentCaptor.forClass(RuntimeTaskRow.class);
        verify(runtimeTaskMapper).insert(captor.capture());
        RuntimeTaskRow inserted = captor.getValue();
        assertThat(inserted.id()).isEqualTo(view.taskId());
        assertThat(inserted.userPublicId()).isEqualTo(USER_ID);
        assertThat(inserted.resolvedModel()).isEqualTo("openai:gpt-4o-mini");
        assertThat(inserted.status()).isEqualTo("ACTIVE");
    }

    @Test
    void createTask_shouldUseDefaultModelWhenRequestIsBlank() {
        ResolvedModel model = new ResolvedModel("openai", "gpt-4o-mini", "GPT-4o mini", List.of("text"), 128000);
        when(modelCatalogService.resolveAuto(USER_ID)).thenReturn(model);
        when(quotaMapper.tryConsume(eq(USER_ID), any(LocalDate.class), anyInt())).thenReturn(new QuotaRow(1, 2));

        service.createTask(USER_ID, "t-1", null, null);

        verify(modelCatalogService).resolveAuto(USER_ID);
        verify(modelCatalogService, never()).requireAvailable(any(), any());
    }

    @Test
    void createTask_shouldThrowQuotaExceededWithDetail_whenQuotaIsFull() {
        ResolvedModel model = new ResolvedModel("openai", "gpt-4o-mini", "GPT-4o mini", List.of("text"), 128000);
        when(modelCatalogService.resolveAuto(USER_ID)).thenReturn(model);
        when(quotaMapper.tryConsume(eq(USER_ID), any(LocalDate.class), anyInt())).thenReturn(null);
        when(quotaMapper.find(eq(USER_ID), any(LocalDate.class))).thenReturn(new QuotaRow(2, 2));

        assertThatThrownBy(() -> service.createTask(USER_ID, "t-1", null, null))
                .isInstanceOfSatisfying(BusinessException.class, ex -> {
                    assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.QUOTA_EXCEEDED);
                    QuotaExceededDetail detail = (QuotaExceededDetail) ex.getPayload();
                    assertThat(detail.quotaType()).isEqualTo("daily_requests");
                    assertThat(detail.limit()).isEqualTo(2);
                    assertThat(detail.used()).isEqualTo(2);
                    assertThat(detail.resetAt()).isEqualTo(OffsetDateTime.parse("2026-10-31T00:00:00Z"));
                });
    }

    @Test
    void createTask_shouldReturnExistingTaskWithoutConsumingQuota_whenSameKeyIsReplayed() {
        when(runtimeTaskMapper.findByUserAndKey(USER_ID, "idem-1")).thenReturn(activeTask("idem-1"));
        when(modelCatalogService.findCapabilities("openai:gpt-4o-mini"))
                .thenReturn(List.of("text", "reasoning"));

        ModelTaskView view = service.createTask(USER_ID, "t-1", "openai:gpt-4o-mini", "idem-1");

        assertThat(view.taskId()).isEqualTo(TASK_ID);
        assertThat(view.modelKey()).isEqualTo("openai:gpt-4o-mini");
        // 幂等重放没有重新解析模型，能力位必须按引用回查后补齐
        assertThat(view.capabilities()).containsExactly("text", "reasoning");
        verify(quotaMapper, never()).tryConsume(any(), any(), anyInt());
        verify(runtimeTaskMapper, never()).insert(any());
    }

    @Test
    void createTask_shouldReject_whenSameKeyIsReusedForAnotherModel() {
        when(runtimeTaskMapper.findByUserAndKey(USER_ID, "idem-1")).thenReturn(activeTask("idem-1"));

        assertThatThrownBy(() -> service.createTask(USER_ID, "t-1", "openai:gpt-4o", "idem-1"))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.IDEMPOTENCY_CONFLICT));
        verify(quotaMapper, never()).tryConsume(any(), any(), anyInt());
    }

    @Test
    void createTask_shouldReject_whenSameKeyTaskHasExpired() {
        RuntimeTaskRow expired = new RuntimeTaskRow(
                TASK_ID, USER_ID, "t-1", "openai:gpt-4o-mini", "openai:gpt-4o-mini", "MANAGED",
                null, null, "ACTIVE", OffsetDateTime.parse("2026-10-30T07:59:00Z"),
                OffsetDateTime.parse("2026-10-30T07:49:00Z"), "idem-1");
        when(runtimeTaskMapper.findByUserAndKey(USER_ID, "idem-1")).thenReturn(expired);

        assertThatThrownBy(() -> service.createTask(USER_ID, "t-1", "openai:gpt-4o-mini", "idem-1"))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.IDEMPOTENCY_CONFLICT));
        verify(quotaMapper, never()).tryConsume(any(), any(), anyInt());
    }

    @Test
    void createTask_shouldReuseTaskCreatedByConcurrentRequest_whenInsertConflicts() {
        ResolvedModel model = new ResolvedModel("openai", "gpt-4o-mini", "GPT-4o mini", List.of("text"), 128000);
        when(modelCatalogService.requireAvailable("openai:gpt-4o-mini", USER_ID)).thenReturn(model);
        // 第一次预查未命中，插入撞唯一索引后回读到对方已提交的任务
        when(runtimeTaskMapper.findByUserAndKey(USER_ID, "idem-1"))
                .thenReturn(null, activeTask("idem-1"));
        when(runtimeTaskMapper.insert(any(RuntimeTaskRow.class))).thenReturn(0);

        ModelTaskView view = service.createTask(USER_ID, "t-1", "openai:gpt-4o-mini", "idem-1");

        assertThat(view.taskId()).isEqualTo(TASK_ID);
        verify(quotaMapper, never()).tryConsume(any(), any(), anyInt());
    }

    @Test
    void createTask_shouldPersistIdempotencyKey_whenProvided() {
        ResolvedModel model = new ResolvedModel("openai", "gpt-4o-mini", "GPT-4o mini", List.of("text"), 128000);
        when(modelCatalogService.requireAvailable("openai:gpt-4o-mini", USER_ID)).thenReturn(model);
        when(quotaMapper.tryConsume(USER_ID, LocalDate.of(2026, 10, 30), 2)).thenReturn(new QuotaRow(1, 2));
        when(runtimeTaskMapper.insert(any(RuntimeTaskRow.class))).thenReturn(1);

        service.createTask(USER_ID, "t-1", "openai:gpt-4o-mini", "idem-1");

        ArgumentCaptor<RuntimeTaskRow> captor = ArgumentCaptor.forClass(RuntimeTaskRow.class);
        verify(runtimeTaskMapper).insert(captor.capture());
        assertThat(captor.getValue().idempotencyKey()).isEqualTo("idem-1");
    }

    @Test
    void expireStaleTasks_shouldReturnMarkedCount() {
        when(runtimeTaskMapper.markExpiredBefore(OffsetDateTime.parse("2026-10-30T08:00:00Z"))).thenReturn(3);

        assertThat(service.expireStaleTasks()).isEqualTo(3);
    }

    @Test
    void createTask_shouldPropagateModelNotAvailable() {
        when(modelCatalogService.requireAvailable("openai:unknown", USER_ID)).thenThrow(
                new BusinessException(ModelErrorCode.MODEL_NOT_AVAILABLE));

        assertThatThrownBy(() -> service.createTask(USER_ID, "t-1", "openai:unknown", null))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.MODEL_NOT_AVAILABLE));
        verify(quotaMapper, never()).tryConsume(any(), any(), anyInt());
    }

    @Test
    void createTask_shouldReturnNotFound_whenRuntimeIsDisabled() {
        properties.setRuntimeEnabled(false);

        assertThatThrownBy(() -> service.createTask(USER_ID, "t-1", null, null))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.RUNTIME_DISABLED));
        verify(quotaMapper, never()).tryConsume(any(), any(), anyInt());
    }

    @Test
    void createTask_shouldUseByokAndConsumeSharedQuota_whenActiveConnectionExists() {
        properties.setByokEnabled(true);
        ResolvedModel model = new ResolvedModel("openai", "gpt-4o-mini", "GPT-4o mini", List.of("text"), 128000);
        when(modelCatalogService.requireAvailable("openai:gpt-4o-mini", USER_ID)).thenReturn(model);
        when(connectionMapper.findActiveViewByProvider(USER_ID, "openai"))
                .thenReturn(connectionView(CREDENTIAL_ID, BYOK_BASE_URL));
        when(quotaMapper.tryConsume(USER_ID, LocalDate.of(2026, 10, 30), 2)).thenReturn(new QuotaRow(1, 2));
        when(runtimeTaskMapper.insert(any(RuntimeTaskRow.class))).thenReturn(1);

        ModelTaskView view = service.createTask(USER_ID, "t-1", "openai:gpt-4o-mini", null);

        assertThat(view.credentialSource()).isEqualTo("BYOK");
        assertThat(view.credentialId()).isEqualTo(CREDENTIAL_ID);
        assertThat(view.baseUrl()).isEqualTo(BYOK_BASE_URL);
        // BYOK 与平台托管凭证共用同一每日额度，必须同样扣减
        verify(quotaMapper).tryConsume(USER_ID, LocalDate.of(2026, 10, 30), 2);

        ArgumentCaptor<RuntimeTaskRow> captor = ArgumentCaptor.forClass(RuntimeTaskRow.class);
        verify(runtimeTaskMapper).insert(captor.capture());
        assertThat(captor.getValue().credentialSource()).isEqualTo("BYOK");
        assertThat(captor.getValue().credentialId()).isEqualTo(CREDENTIAL_ID);
        assertThat(captor.getValue().baseUrl()).isEqualTo(BYOK_BASE_URL);
    }

    @Test
    void createTask_shouldThrowQuotaExceeded_whenByokAndQuotaIsFull() {
        properties.setByokEnabled(true);
        ResolvedModel model = new ResolvedModel("openai", "gpt-4o-mini", "GPT-4o mini", List.of("text"), 128000);
        when(modelCatalogService.resolveAuto(USER_ID)).thenReturn(model);
        when(connectionMapper.findActiveViewByProvider(USER_ID, "openai"))
                .thenReturn(connectionView(CREDENTIAL_ID, BYOK_BASE_URL));
        when(quotaMapper.tryConsume(eq(USER_ID), any(LocalDate.class), anyInt())).thenReturn(null);
        when(quotaMapper.find(eq(USER_ID), any(LocalDate.class))).thenReturn(new QuotaRow(2, 2));
        when(runtimeTaskMapper.insert(any(RuntimeTaskRow.class))).thenReturn(1);

        assertThatThrownBy(() -> service.createTask(USER_ID, "t-1", null, null))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.QUOTA_EXCEEDED));
        // 任务先落库再扣额度：额度不足时抛异常，真实事务会回滚任务插入
        verify(quotaMapper).find(eq(USER_ID), any(LocalDate.class));
    }

    @Test
    void createTask_shouldThrowCredentialRevokedWithoutConsumingQuota_whenConnectionHasNoCredential() {
        properties.setByokEnabled(true);
        ResolvedModel model = new ResolvedModel("openai", "gpt-4o-mini", "GPT-4o mini", List.of("text"), 128000);
        when(modelCatalogService.requireAvailable("openai:gpt-4o-mini", USER_ID)).thenReturn(model);
        when(connectionMapper.findActiveViewByProvider(USER_ID, "openai"))
                .thenReturn(connectionView(null, BYOK_BASE_URL));

        assertThatThrownBy(() -> service.createTask(USER_ID, "t-1", "openai:gpt-4o-mini", null))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.CREDENTIAL_REVOKED));
        // 凭证不可用时不能先扣额度，否则用户重试仍然白扣
        verify(quotaMapper, never()).tryConsume(any(), any(), anyInt());
        verify(runtimeTaskMapper, never()).insert(any());
    }

    @Test
    void readTask_shouldReturnView_whenTaskBelongsToUser() {
        RuntimeTaskRow row = new RuntimeTaskRow(
                TASK_ID, USER_ID, "t-1", null, "openai:gpt-4o-mini", "MANAGED", null, null,
                "ACTIVE", OffsetDateTime.parse("2026-10-30T08:10:00Z"), OffsetDateTime.parse("2026-10-30T08:00:00Z"), null);
        when(runtimeTaskMapper.findByIds(List.of(TASK_ID))).thenReturn(List.of(row));
        when(modelCatalogService.findCapabilities("openai:gpt-4o-mini"))
                .thenReturn(List.of("text", "reasoning_visible"));

        ModelTaskView view = service.readTask(USER_ID, TASK_ID);

        assertThat(view.taskId()).isEqualTo(TASK_ID);
        assertThat(view.provider()).isEqualTo("openai");
        assertThat(view.modelKey()).isEqualTo("openai:gpt-4o-mini");
        assertThat(view.capabilities()).containsExactly("text", "reasoning_visible");
    }

    @Test
    void readTask_shouldReturnNotFound_whenTaskBelongsToAnotherUser() {
        RuntimeTaskRow row = new RuntimeTaskRow(
                TASK_ID, UUID.randomUUID(), "t-1", null, "openai:gpt-4o-mini", "MANAGED", null, null,
                "ACTIVE", OffsetDateTime.parse("2026-10-30T08:10:00Z"), OffsetDateTime.parse("2026-10-30T08:00:00Z"), null);
        when(runtimeTaskMapper.findByIds(List.of(TASK_ID))).thenReturn(List.of(row));

        assertThatThrownBy(() -> service.readTask(USER_ID, TASK_ID))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.TASK_NOT_FOUND));
    }

    @Test
    void readTask_shouldReturnNotFound_whenTaskExpired() {
        RuntimeTaskRow row = new RuntimeTaskRow(
                TASK_ID, USER_ID, "t-1", null, "openai:gpt-4o-mini", "MANAGED", null, null,
                "ACTIVE", OffsetDateTime.parse("2026-10-30T07:59:00Z"), OffsetDateTime.parse("2026-10-30T07:49:00Z"), null);
        when(runtimeTaskMapper.findByIds(List.of(TASK_ID))).thenReturn(List.of(row));

        assertThatThrownBy(() -> service.readTask(USER_ID, TASK_ID))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.TASK_NOT_FOUND));
    }

    private static RuntimeTaskRow activeTask(String idempotencyKey) {
        return new RuntimeTaskRow(
                TASK_ID, USER_ID, "t-1", "openai:gpt-4o-mini", "openai:gpt-4o-mini", "MANAGED",
                null, null, "ACTIVE", OffsetDateTime.parse("2026-10-30T08:10:00Z"),
                OffsetDateTime.parse("2026-10-30T08:00:00Z"), idempotencyKey);
    }

    private static ProviderConnectionViewRow connectionView(UUID credentialId, String baseUrl) {
        OffsetDateTime createdAt = OffsetDateTime.parse("2026-10-30T08:00:00Z");
        return new ProviderConnectionViewRow(
                UUID.randomUUID(), "openai", "OpenAI", baseUrl, "ACTIVE", null, createdAt,
                credentialId, credentialId == null ? null : "sk-****7890",
                credentialId == null ? null : "VERIFIED", credentialId == null ? null : createdAt);
    }
}
