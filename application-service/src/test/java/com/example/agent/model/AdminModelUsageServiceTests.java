package com.example.agent.model;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatExceptionOfType;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.example.agent.model.application.AdminModelUsageService;
import com.example.agent.model.infrastructure.AdminModelUsageMapper;
import com.example.agent.model.infrastructure.AdminUsageFilter;
import com.example.agent.model.infrastructure.AdminUsageModelRow;
import com.example.agent.model.infrastructure.AdminUsageProviderRow;
import com.example.agent.model.infrastructure.AdminUsageRow;
import com.example.agent.model.infrastructure.AdminUsageStatusRow;
import com.example.agent.model.infrastructure.AdminUsageTotalsRow;
import com.example.agent.model.web.dto.AdminModelUsageQuery;
import com.example.agent.model.web.dto.AdminModelUsageSummaryQuery;
import com.example.agent.model.web.dto.AdminModelUsageSummaryResponse;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 管理端用量查询服务单测：不启动容器，数据访问全部隔离。
 *
 * <p>覆盖分页映射、空结果、参数校验、过滤条件下推与多币种金额置空规则。</p>
 */
@ExtendWith(MockitoExtension.class)
class AdminModelUsageServiceTests {

    private static final UUID USER_ID = UUID.fromString("11111111-1111-1111-1111-111111111111");
    private static final UUID INVOCATION_ID = UUID.fromString("22222222-2222-2222-2222-222222222222");
    private static final OffsetDateTime OCCURRED_AT =
            OffsetDateTime.of(2026, 11, 1, 8, 30, 0, 0, ZoneOffset.UTC);

    @Mock
    private AdminModelUsageMapper adminModelUsageMapper;

    @InjectMocks
    private AdminModelUsageService adminModelUsageService;

    @Test
    void listUsage_shouldMapRowsAndPushFiltersIntoQuery() {
        AdminModelUsageQuery query = new AdminModelUsageQuery();
        query.setUserId(USER_ID.toString());
        query.setProvider("openai");
        query.setOrder("asc");
        query.setSize(10);
        when(adminModelUsageMapper.count(any())).thenReturn(1L);
        when(adminModelUsageMapper.findPage(any(), anyLong(), anyInt()))
                .thenReturn(List.of(usageRow()));

        var page = adminModelUsageService.list(query);

        ArgumentCaptor<AdminUsageFilter> filterCaptor =
                ArgumentCaptor.forClass(AdminUsageFilter.class);
        verify(adminModelUsageMapper).count(filterCaptor.capture());
        AdminUsageFilter filter = filterCaptor.getValue();
        assertThat(filter.userId()).isEqualTo(USER_ID);
        assertThat(filter.provider()).isEqualTo("openai");
        assertThat(filter.ascending()).isTrue();
        assertThat(page.total()).isEqualTo(1);
        assertThat(page.page()).isEqualTo(1);
        assertThat(page.size()).isEqualTo(10);
        assertThat(page.list()).singleElement().satisfies(item -> {
            assertThat(item.userId()).isEqualTo(USER_ID);
            assertThat(item.username()).isEqualTo("demo");
            assertThat(item.invocationId()).isEqualTo(INVOCATION_ID);
        });
    }

    @Test
    void listUsage_shouldReturnEmptyPage_whenNothingMatches() {
        AdminModelUsageQuery query = new AdminModelUsageQuery();
        when(adminModelUsageMapper.count(any())).thenReturn(0L);

        var page = adminModelUsageService.list(query);

        assertThat(page.list()).isEmpty();
        assertThat(page.total()).isZero();
        verify(adminModelUsageMapper, never()).findPage(any(), anyLong(), anyInt());
    }

    @Test
    void listUsage_shouldRejectMalformedUserId() {
        AdminModelUsageQuery query = new AdminModelUsageQuery();
        query.setUserId("not-a-uuid");

        assertThatExceptionOfType(BusinessException.class)
                .isThrownBy(() -> adminModelUsageService.list(query))
                .satisfies(exception -> assertThat(exception.getErrorCode())
                        .isEqualTo(CommonErrorCode.PARAM_INVALID));
        verifyNoInteractions(adminModelUsageMapper);
    }

    @Test
    void listUsage_shouldRejectInvertedDateRange() {
        AdminModelUsageQuery query = new AdminModelUsageQuery();
        query.setFrom(LocalDate.of(2026, 11, 2));
        query.setTo(LocalDate.of(2026, 11, 1));

        assertThatExceptionOfType(BusinessException.class)
                .isThrownBy(() -> adminModelUsageService.list(query))
                .satisfies(exception -> assertThat(exception.getErrorCode())
                        .isEqualTo(CommonErrorCode.PARAM_INVALID));
        verifyNoInteractions(adminModelUsageMapper);
    }

    @Test
    void summarize_shouldKeepAmountAndCurrency_whenSingleCurrency() {
        stubSummary(defaultTotals(), List.of(statusRow("ESTIMATED", "USD", 1, "12.5")),
                List.of(providerRow("openai", "USD", 1, "12.5")),
                List.of(modelRow("openai", "gpt-4o-mini", "USD", 1, "12.5")));

        AdminModelUsageSummaryResponse response = adminModelUsageService.summarize(newQuery());

        assertThat(response.totals().estimatedCost()).isEqualByComparingTo("12.5");
        assertThat(response.totals().currency()).isEqualTo("USD");
        assertThat(response.totals().estimatedCount()).isEqualTo(2);
        assertThat(response.byCostStatus()).singleElement().satisfies(item -> {
            assertThat(item.costStatus()).isEqualTo("ESTIMATED");
            assertThat(item.estimatedCost()).isEqualByComparingTo("12.5");
        });
        assertThat(response.byProvider()).singleElement()
                .satisfies(item -> assertThat(item.totalTokens()).isEqualTo(300));
        assertThat(response.byModel()).singleElement()
                .satisfies(item -> assertThat(item.modelKey()).isEqualTo("gpt-4o-mini"));
    }

    @Test
    void summarize_shouldBlankAmount_whenMultipleCurrencies() {
        stubSummary(multiCurrencyTotals(), List.of(statusRow("ESTIMATED", "USD", 2, "12.5")),
                List.of(providerRow("openai", "USD", 2, "12.5")),
                List.of(modelRow("openai", "gpt-4o-mini", "USD", 2, "12.5")));

        AdminModelUsageSummaryResponse response = adminModelUsageService.summarize(newQuery());

        assertThat(response.totals().estimatedCost()).isNull();
        assertThat(response.totals().currency()).isNull();
        assertThat(response.byCostStatus()).singleElement()
                .satisfies(item -> assertThat(item.estimatedCost()).isNull());
        assertThat(response.byProvider()).singleElement()
                .satisfies(item -> assertThat(item.currency()).isNull());
        assertThat(response.byModel()).singleElement()
                .satisfies(item -> assertThat(item.estimatedCost()).isNull());
    }

    @Test
    void summarize_shouldReturnZeros_whenNoRecords() {
        stubSummary(new AdminUsageTotalsRow(0L, 0L, 0L, null, null, null, 0, null),
                List.of(), List.of(), List.of());

        AdminModelUsageSummaryResponse response = adminModelUsageService.summarize(newQuery());

        assertThat(response.totals().requestCount()).isZero();
        assertThat(response.totals().promptTokens()).isZero();
        assertThat(response.totals().completionTokens()).isZero();
        assertThat(response.totals().totalTokens()).isZero();
        assertThat(response.totals().estimatedCost()).isNull();
        assertThat(response.byCostStatus()).isEmpty();
        assertThat(response.byProvider()).isEmpty();
        assertThat(response.byModel()).isEmpty();
    }

    private void stubSummary(
            AdminUsageTotalsRow totals,
            List<AdminUsageStatusRow> statusRows,
            List<AdminUsageProviderRow> providerRows,
            List<AdminUsageModelRow> modelRows) {
        when(adminModelUsageMapper.summarizeTotals(any())).thenReturn(totals);
        when(adminModelUsageMapper.summarizeByCostStatus(any())).thenReturn(statusRows);
        when(adminModelUsageMapper.summarizeByProvider(any(), anyInt())).thenReturn(providerRows);
        when(adminModelUsageMapper.summarizeByModel(any(), anyInt())).thenReturn(modelRows);
    }

    private static AdminModelUsageSummaryQuery newQuery() {
        AdminModelUsageSummaryQuery query = new AdminModelUsageSummaryQuery();
        query.setFrom(LocalDate.of(2026, 11, 1));
        query.setTo(LocalDate.of(2026, 11, 2));
        return query;
    }

    private static AdminUsageRow usageRow() {
        return new AdminUsageRow(
                INVOCATION_ID,
                UUID.fromString("33333333-3333-3333-3333-333333333333"),
                USER_ID,
                "demo",
                "thread-1",
                "chat",
                "openai",
                "gpt-4o-mini",
                "MANAGED",
                100,
                200,
                1500,
                "success",
                null,
                new BigDecimal("0.5"),
                "ESTIMATED",
                "PLATFORM",
                "USD",
                OCCURRED_AT);
    }

    private static AdminUsageTotalsRow defaultTotals() {
        return new AdminUsageTotalsRow(2L, 1L, 1L, 100L, 200L, new BigDecimal("12.5"), 1, "USD");
    }

    private static AdminUsageTotalsRow multiCurrencyTotals() {
        return new AdminUsageTotalsRow(2L, 1L, 1L, 100L, 200L, new BigDecimal("12.5"), 2, "USD");
    }

    private static AdminUsageStatusRow statusRow(
            String costStatus, String currency, int currencyCount, String cost) {
        return new AdminUsageStatusRow(costStatus, 2L,
                cost == null ? null : new BigDecimal(cost), currency, currencyCount);
    }

    private static AdminUsageProviderRow providerRow(
            String provider, String currency, int currencyCount, String cost) {
        return new AdminUsageProviderRow(provider, 2L, 100L, 200L,
                cost == null ? null : new BigDecimal(cost), currency, currencyCount);
    }

    private static AdminUsageModelRow modelRow(
            String provider, String modelKey, String currency, int currencyCount, String cost) {
        return new AdminUsageModelRow(provider, modelKey, 2L, 100L, 200L,
                cost == null ? null : new BigDecimal(cost), currency, currencyCount);
    }
}
