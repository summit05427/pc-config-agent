package com.example.agent.model;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyCollection;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.agent.model.application.ModelRuntimeGuard;
import com.example.agent.model.application.ModelUsageService;
import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.model.domain.UsageRecordInput;
import com.example.agent.model.domain.UsageReportResult;
import com.example.agent.model.infrastructure.ModelPricingMapper;
import com.example.agent.model.infrastructure.ModelPricingRow;
import com.example.agent.model.infrastructure.PricingStore;
import com.example.agent.model.infrastructure.RuntimeTaskMapper;
import com.example.agent.model.infrastructure.RuntimeTaskRow;
import com.example.agent.model.infrastructure.RuntimeTaskStore;
import com.example.agent.model.infrastructure.UsageMapper;
import com.example.agent.model.infrastructure.UsageRecordRow;
import com.example.agent.model.infrastructure.UsageStore;
import com.example.agent.shared.config.ModelRuntimeProperties;
import com.example.agent.shared.error.BusinessException;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 使用明细入库单测：归属与一致性由任务行推导，重复 invocationId 只入库一次，
 * 成本由服务端按定价版本计算；缺数据时标记 {@code UNKNOWN} 而不是写 0。
 */
@ExtendWith(MockitoExtension.class)
class ModelUsageServiceTests {

    private static final UUID TASK_ID = UUID.fromString("9d2a6b4a-1c58-4d9a-9a54-2f6a8c1f0b21");

    private static final UUID USER_ID = UUID.fromString("6f5a0b36-64c6-4f38-8a9d-53e1a2c9a742");

    private static final OffsetDateTime OCCURRED_AT = OffsetDateTime.parse("2026-10-30T08:00:05Z");

    @Mock
    private RuntimeTaskMapper runtimeTaskMapper;

    @Mock
    private UsageMapper usageMapper;

    @Mock
    private ModelPricingMapper modelPricingMapper;

    private ModelRuntimeProperties properties;

    private ModelUsageService service;

    @BeforeEach
    void setUp() {
        properties = new ModelRuntimeProperties();
        properties.setRuntimeEnabled(true);
        // 真实 Store 包住被 mock 的 mapper，保留原有对底层调用的断言
        service = new ModelUsageService(
                new RuntimeTaskStore(runtimeTaskMapper), new UsageStore(usageMapper),
                new PricingStore(modelPricingMapper), new ModelRuntimeGuard(properties));
    }

    @Test
    void report_shouldAcceptMatchingRecordAndRejectUnknownTask() {
        when(runtimeTaskMapper.findByIds(anyCollection())).thenReturn(List.of(task("MANAGED")));
        when(usageMapper.insertIgnoreDuplicates(anyList())).thenReturn(1);

        UsageReportResult result = service.report(List.of(
                record("openai:gpt-4o-mini", "MANAGED", TASK_ID),
                record("openai:gpt-4o-mini", "MANAGED", UUID.randomUUID())));

        assertThat(result.accepted()).isEqualTo(1);
        assertThat(result.duplicated()).isZero();
        assertThat(result.rejected()).isEqualTo(1);

        UsageRecordRow row = captureRow();
        // 归属与线程 ID 取自任务行，而不是上报方字段
        assertThat(row.userPublicId()).isEqualTo(USER_ID);
        assertThat(row.threadId()).isEqualTo("t-1");
        assertThat(row.provider()).isEqualTo("openai");
        assertThat(row.modelKey()).isEqualTo("gpt-4o-mini");
    }

    @Test
    void report_shouldCountDuplicatedWhenInsertSkipsRows() {
        when(runtimeTaskMapper.findByIds(anyCollection())).thenReturn(List.of(task("MANAGED")));
        when(usageMapper.insertIgnoreDuplicates(anyList())).thenReturn(0);

        UsageReportResult result = service.report(List.of(record("openai:gpt-4o-mini", "MANAGED", TASK_ID)));

        assertThat(result.accepted()).isZero();
        assertThat(result.duplicated()).isEqualTo(1);
        assertThat(result.rejected()).isZero();
    }

    @Test
    void report_shouldRejectCredentialSourceMismatch() {
        when(runtimeTaskMapper.findByIds(anyCollection())).thenReturn(List.of(task("MANAGED")));

        UsageReportResult result = service.report(List.of(record("openai:gpt-4o-mini", "BYOK", TASK_ID)));

        assertThat(result.rejected()).isEqualTo(1);
        verify(usageMapper, never()).insertIgnoreDuplicates(anyList());
    }

    @Test
    void report_shouldRejectModelMismatch() {
        when(runtimeTaskMapper.findByIds(anyCollection())).thenReturn(List.of(task("MANAGED")));

        UsageReportResult result = service.report(List.of(record("openai:gpt-4o", "MANAGED", TASK_ID)));

        assertThat(result.rejected()).isEqualTo(1);
        verify(usageMapper, never()).insertIgnoreDuplicates(anyList());
    }

    @Test
    void report_shouldRejectMalformedModelReference() {
        when(runtimeTaskMapper.findByIds(anyCollection())).thenReturn(List.of(task("MANAGED")));

        UsageReportResult result = service.report(List.of(record("gpt-4o-mini", "MANAGED", TASK_ID)));

        assertThat(result.rejected()).isEqualTo(1);
        verify(usageMapper, never()).insertIgnoreDuplicates(anyList());
    }

    @Test
    void report_shouldNotCallMapper_whenAllRecordsRejected() {
        when(runtimeTaskMapper.findByIds(anyCollection())).thenReturn(List.of());

        UsageReportResult result = service.report(List.of(record("openai:gpt-4o-mini", "MANAGED", TASK_ID)));

        assertThat(result.rejected()).isEqualTo(1);
        verify(usageMapper, never()).insertIgnoreDuplicates(anyList());
    }

    @Test
    void report_shouldReturnNotFound_whenRuntimeIsDisabled() {
        properties.setRuntimeEnabled(false);

        assertThatThrownBy(() -> service.report(List.of(record("openai:gpt-4o-mini", "MANAGED", TASK_ID))))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.RUNTIME_DISABLED));
    }

    @Test
    void report_shouldMarkByokCostAsNotBilledByPlatform() {
        when(runtimeTaskMapper.findByIds(anyCollection())).thenReturn(List.of(task("BYOK")));
        when(usageMapper.insertIgnoreDuplicates(anyList())).thenReturn(1);

        service.report(List.of(record("openai:gpt-4o-mini", "BYOK", TASK_ID)));

        UsageRecordRow row = captureRow();
        // BYOK 由用户承担费用，平台不估算金额，避免把用户成本算进平台账
        assertThat(row.costStatus()).isEqualTo("BYOK_NOT_BILLED");
        assertThat(row.costBearer()).isEqualTo("USER");
        assertThat(row.estimatedCost()).isNull();
        assertThat(row.currency()).isNull();
    }

    @Test
    void report_shouldEstimateCostByEffectivePricingVersion() {
        when(runtimeTaskMapper.findByIds(anyCollection())).thenReturn(List.of(task("MANAGED")));
        when(modelPricingMapper.findByModels(anyCollection(), anyCollection()))
                .thenReturn(List.of(price("2026-10-30T09:00:00Z", "1.0", "2.0"),
                        price("2026-10-01T00:00:00Z", "0.15", "0.60")));
        when(usageMapper.insertIgnoreDuplicates(anyList())).thenReturn(1);

        service.report(List.of(record("openai:gpt-4o-mini", "MANAGED", TASK_ID)));

        UsageRecordRow row = captureRow();
        // 取「不晚于调用时刻」的最近版本：120 输入 × 0.15 + 30 输出 × 0.60，单位每百万 token
        assertThat(row.costStatus()).isEqualTo("ESTIMATED");
        assertThat(row.costBearer()).isEqualTo("PLATFORM");
        assertThat(row.currency()).isEqualTo("USD");
        assertThat(row.estimatedCost()).isEqualByComparingTo(new BigDecimal("0.000036"));
    }

    @Test
    void report_shouldMarkCostUnknown_whenNoEffectivePricing() {
        when(runtimeTaskMapper.findByIds(anyCollection())).thenReturn(List.of(task("MANAGED")));
        when(usageMapper.insertIgnoreDuplicates(anyList())).thenReturn(1);

        service.report(List.of(record("openai:gpt-4o-mini", "MANAGED", TASK_ID)));

        UsageRecordRow row = captureRow();
        assertThat(row.costStatus()).isEqualTo("UNKNOWN");
        assertThat(row.costBearer()).isEqualTo("PLATFORM");
        // 没有定价时保留未知，绝不写 0 冒充已知成本
        assertThat(row.estimatedCost()).isNull();
        assertThat(row.currency()).isNull();
    }

    @Test
    void report_shouldMarkCostUnknown_whenTokenUsageMissing() {
        when(runtimeTaskMapper.findByIds(anyCollection())).thenReturn(List.of(task("MANAGED")));
        when(modelPricingMapper.findByModels(anyCollection(), anyCollection()))
                .thenReturn(List.of(price("2026-10-01T00:00:00Z", "0.15", "0.60")));
        when(usageMapper.insertIgnoreDuplicates(anyList())).thenReturn(1);

        service.report(List.of(recordWithoutTokens("openai:gpt-4o-mini", TASK_ID)));

        UsageRecordRow row = captureRow();
        assertThat(row.costStatus()).isEqualTo("UNKNOWN");
        assertThat(row.estimatedCost()).isNull();
    }

    private UsageRecordRow captureRow() {
        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<UsageRecordRow>> captor = ArgumentCaptor.forClass(List.class);
        verify(usageMapper).insertIgnoreDuplicates(captor.capture());
        return captor.getValue().get(0);
    }

    private RuntimeTaskRow task(String credentialSource) {
        return new RuntimeTaskRow(
                TASK_ID, USER_ID, "t-1", null, "openai:gpt-4o-mini", credentialSource, null, null,
                "ACTIVE", OffsetDateTime.parse("2026-10-30T08:10:00Z"), OffsetDateTime.parse("2026-10-30T08:00:00Z"), null);
    }

    private ModelPricingRow price(String effectiveFrom, String input, String output) {
        return new ModelPricingRow(
                "openai", "gpt-4o-mini", "USD",
                new BigDecimal(input), new BigDecimal(output), OffsetDateTime.parse(effectiveFrom));
    }

    private UsageRecordInput record(String modelKey, String credentialSource, UUID taskId) {
        return new UsageRecordInput(
                UUID.randomUUID(), taskId, "conversation", modelKey.split(":")[0], modelKey, credentialSource,
                120, 30, 850, "success", null, OCCURRED_AT);
    }

    private UsageRecordInput recordWithoutTokens(String modelKey, UUID taskId) {
        return new UsageRecordInput(
                UUID.randomUUID(), taskId, "conversation", modelKey.split(":")[0], modelKey, "MANAGED",
                null, null, 850, "success", null, OCCURRED_AT);
    }
}
