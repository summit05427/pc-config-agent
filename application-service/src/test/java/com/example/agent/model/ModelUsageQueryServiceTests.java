package com.example.agent.model;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.agent.model.application.ModelRuntimeGuard;
import com.example.agent.model.application.ModelUsageQueryService;
import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.model.domain.ModelUsageQueryResult;
import com.example.agent.model.infrastructure.QuotaMapper;
import com.example.agent.model.infrastructure.QuotaRow;
import com.example.agent.model.infrastructure.QuotaStore;
import com.example.agent.model.infrastructure.UsageMapper;
import com.example.agent.model.infrastructure.UsageRecordRow;
import com.example.agent.model.infrastructure.UsageStore;
import com.example.agent.shared.config.ModelRuntimeProperties;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 本人用量查询单测：归属只取令牌主体、分页与日期过滤边界、额度快照回落。
 */
@ExtendWith(MockitoExtension.class)
class ModelUsageQueryServiceTests {

    private static final UUID USER_ID = UUID.fromString("6f5a0b36-64c6-4f38-8a9d-53e1a2c9a742");

    private static final Clock FIXED_CLOCK =
            Clock.fixed(Instant.parse("2026-10-31T12:00:00Z"), ZoneOffset.UTC);

    @Mock
    private UsageMapper usageMapper;

    @Mock
    private QuotaMapper quotaMapper;

    private ModelRuntimeProperties properties;

    private ModelUsageQueryService service;

    @BeforeEach
    void setUp() {
        properties = new ModelRuntimeProperties();
        properties.setRuntimeEnabled(true);
        properties.getQuota().setDailyRequests(50);
        // 真实 Store 包住被 mock 的 mapper，保留原有对底层调用的断言
        service = new ModelUsageQueryService(
                new UsageStore(usageMapper), new QuotaStore(quotaMapper),
                new ModelRuntimeGuard(properties), properties, FIXED_CLOCK);
    }

    @Test
    void query_shouldReturnQuotaSnapshotAndMappedItems() {
        when(usageMapper.countByUser(USER_ID, null, null)).thenReturn(2L);
        when(usageMapper.findPage(USER_ID, null, null, 0L, 20)).thenReturn(List.of(
                row("openai", "gpt-4o-mini", "MANAGED"),
                row("deepseek", "deepseek-chat", "BYOK")));
        when(quotaMapper.find(USER_ID, LocalDate.parse("2026-10-31"))).thenReturn(new QuotaRow(3, 100));
        when(usageMapper.sumTokensByUser(USER_ID)).thenReturn(1234L);

        ModelUsageQueryResult result = service.query(USER_ID, null, null, 1, 20);

        assertThat(result.totalTokens()).isEqualTo(1234L);
        assertThat(result.quota().quotaType()).isEqualTo("daily_requests");
        assertThat(result.quota().used()).isEqualTo(3);
        assertThat(result.quota().limit()).isEqualTo(100);
        assertThat(result.quota().resetAt()).isEqualTo(OffsetDateTime.parse("2026-11-01T00:00:00Z"));
        assertThat(result.total()).isEqualTo(2);
        assertThat(result.page()).isEqualTo(1);
        assertThat(result.size()).isEqualTo(20);
        assertThat(result.list()).hasSize(2);
        assertThat(result.list().get(1).credentialSource()).isEqualTo("BYOK");
    }

    @Test
    void query_shouldUseConfiguredLimit_whenNoQuotaRow() {
        when(usageMapper.countByUser(USER_ID, null, null)).thenReturn(0L);
        when(usageMapper.findPage(USER_ID, null, null, 0L, 20)).thenReturn(List.of());
        when(quotaMapper.find(USER_ID, LocalDate.parse("2026-10-31"))).thenReturn(null);

        ModelUsageQueryResult result = service.query(USER_ID, null, null, 1, 20);

        assertThat(result.quota().used()).isZero();
        assertThat(result.quota().limit()).isEqualTo(50);
    }

    @Test
    void query_shouldConvertDateRangeToUtcHalfOpenWindow() {
        LocalDate from = LocalDate.parse("2026-10-01");
        LocalDate to = LocalDate.parse("2026-10-30");
        when(usageMapper.countByUser(USER_ID, from.atStartOfDay(ZoneOffset.UTC).toOffsetDateTime(),
                to.plusDays(1).atStartOfDay(ZoneOffset.UTC).toOffsetDateTime())).thenReturn(0L);
        when(usageMapper.findPage(USER_ID, from.atStartOfDay(ZoneOffset.UTC).toOffsetDateTime(),
                to.plusDays(1).atStartOfDay(ZoneOffset.UTC).toOffsetDateTime(), 40L, 20)).thenReturn(List.of());
        when(quotaMapper.find(USER_ID, LocalDate.parse("2026-10-31"))).thenReturn(null);

        service.query(USER_ID, from, to, 3, 20);

        // 截止日期含当天：转成次日 00:00 UTC 的开区间，避免漏掉当天数据
        verify(usageMapper).findPage(
                USER_ID,
                OffsetDateTime.parse("2026-10-01T00:00:00Z"),
                OffsetDateTime.parse("2026-10-31T00:00:00Z"),
                40L, 20);
    }

    @Test
    void query_shouldRejectInvalidPageOrSize() {
        assertThatThrownBy(() -> service.query(USER_ID, null, null, 0, 20))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(CommonErrorCode.PARAM_INVALID));
        assertThatThrownBy(() -> service.query(USER_ID, null, null, 1, 101))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(CommonErrorCode.PARAM_INVALID));
    }

    @Test
    void query_shouldRejectReversedDateRange() {
        assertThatThrownBy(() -> service.query(
                USER_ID, LocalDate.parse("2026-10-31"), LocalDate.parse("2026-10-01"), 1, 20))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(CommonErrorCode.PARAM_INVALID));
    }

    @Test
    void query_shouldReturnRuntimeDisabled_whenSwitchOff() {
        properties.setRuntimeEnabled(false);

        assertThatThrownBy(() -> service.query(USER_ID, null, null, 1, 20))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.RUNTIME_DISABLED));
    }

    private UsageRecordRow row(String provider, String modelKey, String credentialSource) {
        return new UsageRecordRow(
                UUID.randomUUID(), UUID.randomUUID(), USER_ID, "t-1", "conversation",
                provider, modelKey, credentialSource, 120, 30, 850, "success", null, null,
                "UNKNOWN", "PLATFORM", null, OffsetDateTime.parse("2026-10-30T08:00:05Z"));
    }
}
