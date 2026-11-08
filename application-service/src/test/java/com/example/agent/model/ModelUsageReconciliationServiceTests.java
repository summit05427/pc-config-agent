package com.example.agent.model;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.example.agent.model.application.ModelUsageReconciliationService;
import com.example.agent.model.domain.ReconciliationResult;
import com.example.agent.model.infrastructure.QuotaMapper;
import com.example.agent.model.infrastructure.UsageMapper;
import com.example.agent.shared.config.ModelRuntimeProperties;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 对账单测：运行时关闭时跳过；统计值按 UTC 当日读取。
 */
@ExtendWith(MockitoExtension.class)
class ModelUsageReconciliationServiceTests {

    /** 固定时钟为 2026-10-31，对账对象是前一 UTC 自然日。 */
    private static final LocalDate RECONCILE_DATE = LocalDate.parse("2026-10-30");

    private static final Clock FIXED_CLOCK =
            Clock.fixed(Instant.parse("2026-10-31T12:00:00Z"), ZoneOffset.UTC);

    @Mock
    private UsageMapper usageMapper;

    @Mock
    private QuotaMapper quotaMapper;

    private ModelRuntimeProperties properties;

    private ModelUsageReconciliationService service;

    @BeforeEach
    void setUp() {
        properties = new ModelRuntimeProperties();
        properties.setRuntimeEnabled(true);
        service = new ModelUsageReconciliationService(usageMapper, quotaMapper, properties, FIXED_CLOCK);
    }

    @Test
    void reconcile_shouldCountAnomaliesForPreviousUtcDay() {
        when(quotaMapper.countOverflow(RECONCILE_DATE)).thenReturn(1);
        when(quotaMapper.countAtLimit(RECONCILE_DATE)).thenReturn(4);
        when(usageMapper.countAttributionMismatches()).thenReturn(2);
        when(usageMapper.countNegativeEstimatedCost()).thenReturn(3);
        when(usageMapper.countCostStatusMismatches()).thenReturn(1);

        ReconciliationResult result = service.reconcile();

        assertThat(result.ran()).isTrue();
        assertThat(result.quotaOverflowUsers()).isEqualTo(1);
        assertThat(result.quotaAtLimitUsers()).isEqualTo(4);
        assertThat(result.attributionMismatches()).isEqualTo(2);
        assertThat(result.negativeEstimatedCost()).isEqualTo(3);
        assertThat(result.costStatusMismatches()).isEqualTo(1);
        assertThat(result.hasAnomaly()).isTrue();
        verify(quotaMapper).countOverflow(RECONCILE_DATE);
        verify(quotaMapper).countAtLimit(RECONCILE_DATE);
    }

    @Test
    void reconcile_shouldSkip_whenRuntimeDisabled() {
        properties.setRuntimeEnabled(false);

        ReconciliationResult result = service.reconcile();

        assertThat(result.ran()).isFalse();
        assertThat(result.hasAnomaly()).isFalse();
        verifyNoInteractions(usageMapper, quotaMapper);
    }
}
