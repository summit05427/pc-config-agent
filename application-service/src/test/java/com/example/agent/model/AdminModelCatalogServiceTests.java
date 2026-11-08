package com.example.agent.model;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatExceptionOfType;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.example.agent.model.application.AdminModelCatalogService;
import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.model.infrastructure.AdminModelCatalogMapper;
import com.example.agent.model.infrastructure.AdminModelRow;
import com.example.agent.model.infrastructure.AdminPricingRow;
import com.example.agent.model.infrastructure.AdminProviderRow;
import com.example.agent.model.web.dto.AdminModelListQuery;
import com.example.agent.model.web.dto.AdminModelPricingCreateRequest;
import com.example.agent.model.web.dto.AdminModelPricingResponse;
import com.example.agent.model.web.dto.AdminModelSummaryResponse;
import com.example.agent.model.web.dto.AdminProviderSummaryResponse;
import com.example.agent.shared.api.PageQuery;
import com.example.agent.shared.api.PageResult;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import tools.jackson.databind.ObjectMapper;

/**
 * 管理端模型目录服务单测：不启动容器，数据访问与 JSON 解析均隔离。
 *
 * <p>覆盖目录过滤、能力解析、最新定价补齐、启停幂等、定价版本冲突与 Provider 启停。</p>
 */
@ExtendWith(MockitoExtension.class)
class AdminModelCatalogServiceTests {

    private static final String PROVIDER = "openai";
    private static final String MODEL_KEY = "gpt-4o-mini";
    private static final Instant EFFECTIVE_FROM = Instant.parse("2026-10-01T00:00:00Z");

    @Mock
    private AdminModelCatalogMapper adminModelCatalogMapper;

    @Mock
    private ObjectMapper objectMapper;

    @InjectMocks
    private AdminModelCatalogService adminModelCatalogService;

    /** 默认让能力解析返回空数组，避免未单独声明的用例走到告警降级分支。 */
    @BeforeEach
    void stubCapabilitiesParser() {
        lenient().when(objectMapper.readValue(anyString(), eq(String[].class)))
                .thenReturn(new String[0]);
    }

    @Test
    void listModels_shouldReturnEmptyPage_whenNoModelMatches() {
        AdminModelListQuery query = modelQuery(" demo ", "", "", 1, 20);
        when(adminModelCatalogMapper.count("%demo%", null, null)).thenReturn(0L);

        PageResult<AdminModelSummaryResponse> result = adminModelCatalogService.listModels(query);

        assertThat(result.list()).isEmpty();
        assertThat(result.total()).isZero();
        verify(adminModelCatalogMapper, never())
                .findPage(any(), any(), any(), anyLong(), anyInt());
    }

    @Test
    void listModels_shouldAttachCapabilitiesAndLatestPricing() throws Exception {
        AdminModelListQuery query = modelQuery("", "", "", 1, 20);
        when(adminModelCatalogMapper.count(null, null, null)).thenReturn(1L);
        when(adminModelCatalogMapper.findPage(null, null, null, 0L, 20))
                .thenReturn(List.of(modelRow(true, true)));
        when(objectMapper.readValue("[\"text\",\"tool_calling\"]", String[].class))
                .thenReturn(new String[] {"text", "tool_calling"});
        when(adminModelCatalogMapper.findLatestPricingByModels(List.of(PROVIDER), List.of(MODEL_KEY)))
                .thenReturn(List.of(pricingRow()));

        PageResult<AdminModelSummaryResponse> result = adminModelCatalogService.listModels(query);

        assertThat(result.total()).isEqualTo(1);
        assertThat(result.list()).singleElement().satisfies(model -> {
            assertThat(model.provider()).isEqualTo(PROVIDER);
            assertThat(model.modelKey()).isEqualTo(MODEL_KEY);
            assertThat(model.capabilities()).containsExactly("text", "tool_calling");
            assertThat(model.enabled()).isTrue();
            assertThat(model.providerEnabled()).isTrue();
            assertThat(model.latestPricing()).isNotNull();
            assertThat(model.latestPricing().currency()).isEqualTo("USD");
            assertThat(model.latestPricing().inputPricePerMillion())
                    .isEqualByComparingTo("0.150000");
        });
    }

    @Test
    void updateModelStatus_shouldRejectMalformedProviderCode() {
        assertThatExceptionOfType(BusinessException.class)
                .isThrownBy(() -> adminModelCatalogService.updateModelStatus("OPENAI", MODEL_KEY, true, "admin"))
                .satisfies(exception -> assertThat(exception.getErrorCode())
                        .isEqualTo(CommonErrorCode.PARAM_INVALID));
        verifyNoInteractions(adminModelCatalogMapper);
    }

    @Test
    void updateModelStatus_shouldRejectMalformedModelKey() {
        assertThatExceptionOfType(BusinessException.class)
                .isThrownBy(() -> adminModelCatalogService.updateModelStatus(PROVIDER, "gpt 4o", true, "admin"))
                .satisfies(exception -> assertThat(exception.getErrorCode())
                        .isEqualTo(CommonErrorCode.PARAM_INVALID));
        verifyNoInteractions(adminModelCatalogMapper);
    }

    @Test
    void updateModelStatus_shouldThrowNotFound_whenModelMissing() {
        when(adminModelCatalogMapper.findByKey(PROVIDER, MODEL_KEY)).thenReturn(null);

        assertThatExceptionOfType(BusinessException.class)
                .isThrownBy(() -> adminModelCatalogService.updateModelStatus(PROVIDER, MODEL_KEY, true, "admin"))
                .satisfies(exception -> assertThat(exception.getErrorCode())
                        .isEqualTo(CommonErrorCode.RESOURCE_NOT_FOUND));
        verify(adminModelCatalogMapper, never()).updateEnabled(any(), any(), anyBoolean());
    }

    @Test
    void updateModelStatus_shouldNotWrite_whenStatusUnchanged() {
        when(adminModelCatalogMapper.findByKey(PROVIDER, MODEL_KEY)).thenReturn(modelRow(true, true));

        AdminModelSummaryResponse result =
                adminModelCatalogService.updateModelStatus(PROVIDER, MODEL_KEY, true, "admin");

        assertThat(result.enabled()).isTrue();
        verify(adminModelCatalogMapper, never()).updateEnabled(any(), any(), anyBoolean());
    }

    @Test
    void updateModelStatus_shouldPersistAndReload_whenStatusChanged() {
        when(adminModelCatalogMapper.findByKey(PROVIDER, MODEL_KEY))
                .thenReturn(modelRow(true, true), modelRow(false, true));
        when(adminModelCatalogMapper.updateEnabled(PROVIDER, MODEL_KEY, false)).thenReturn(1);

        AdminModelSummaryResponse result =
                adminModelCatalogService.updateModelStatus(PROVIDER, MODEL_KEY, false, "admin");

        assertThat(result.enabled()).isFalse();
        verify(adminModelCatalogMapper).updateEnabled(PROVIDER, MODEL_KEY, false);
    }

    @Test
    void listPricing_shouldThrowNotFound_whenModelMissing() {
        when(adminModelCatalogMapper.findByKey(PROVIDER, MODEL_KEY)).thenReturn(null);

        assertThatExceptionOfType(BusinessException.class)
                .isThrownBy(() -> adminModelCatalogService.listPricing(PROVIDER, MODEL_KEY, pageQuery(1, 20)))
                .satisfies(exception -> assertThat(exception.getErrorCode())
                        .isEqualTo(CommonErrorCode.RESOURCE_NOT_FOUND));
        verify(adminModelCatalogMapper, never()).countPricing(any(), any());
    }

    @Test
    void createPricing_shouldRejectDuplicateEffectiveFrom() {
        when(adminModelCatalogMapper.findByKey(PROVIDER, MODEL_KEY)).thenReturn(modelRow(true, true));
        when(adminModelCatalogMapper.findPricingAt(PROVIDER, MODEL_KEY, offsetEffectiveFrom()))
                .thenReturn(pricingRow());

        assertThatExceptionOfType(BusinessException.class)
                .isThrownBy(() -> adminModelCatalogService.createPricing(
                        PROVIDER, MODEL_KEY, pricingRequest(null), "admin"))
                .satisfies(exception -> assertThat(exception.getErrorCode())
                        .isEqualTo(ModelErrorCode.PRICING_VERSION_EXISTS));
        verify(adminModelCatalogMapper, never()).insertPricing(
                any(), any(), any(), any(), any(), any());
    }

    @Test
    void createPricing_shouldDefaultCurrencyToUsdAndReadBack() {
        when(adminModelCatalogMapper.findByKey(PROVIDER, MODEL_KEY)).thenReturn(modelRow(true, true));
        when(adminModelCatalogMapper.findPricingAt(PROVIDER, MODEL_KEY, offsetEffectiveFrom()))
                .thenReturn(null, pricingRow());
        when(adminModelCatalogMapper.insertPricing(
                PROVIDER, MODEL_KEY, "USD", new BigDecimal("0.15"), new BigDecimal("0.60"), offsetEffectiveFrom()))
                .thenReturn(1);

        AdminModelPricingResponse result = adminModelCatalogService.createPricing(
                PROVIDER, MODEL_KEY, pricingRequest(null), "admin");

        assertThat(result.id()).isEqualTo(1L);
        assertThat(result.currency()).isEqualTo("USD");
        assertThat(result.effectiveFrom()).isEqualTo(EFFECTIVE_FROM);
    }

    @Test
    void updateProviderStatus_shouldRejectMalformedCode() {
        assertThatExceptionOfType(BusinessException.class)
                .isThrownBy(() -> adminModelCatalogService.updateProviderStatus("OpenAI", false, "admin"))
                .satisfies(exception -> assertThat(exception.getErrorCode())
                        .isEqualTo(CommonErrorCode.PARAM_INVALID));
        verifyNoInteractions(adminModelCatalogMapper);
    }

    @Test
    void updateProviderStatus_shouldNotWrite_whenStatusUnchanged() {
        when(adminModelCatalogMapper.findProvider(PROVIDER)).thenReturn(providerRow(true));

        AdminProviderSummaryResponse result =
                adminModelCatalogService.updateProviderStatus(PROVIDER, true, "admin");

        assertThat(result.enabled()).isTrue();
        verify(adminModelCatalogMapper, never()).updateProviderEnabled(any(), anyBoolean());
    }

    @Test
    void listProviders_shouldMapCountsAndNormalizeNulls() {
        when(adminModelCatalogMapper.findProviders())
                .thenReturn(List.of(
                        providerRow(true),
                        new AdminProviderRow(
                                PROVIDER, "OpenAI", "openai-compatible", null, null, null, null)));

        List<AdminProviderSummaryResponse> result = adminModelCatalogService.listProviders();

        assertThat(result).hasSize(2);
        assertThat(result.get(0).enabled()).isTrue();
        assertThat(result.get(0).modelCount()).isEqualTo(2L);
        assertThat(result.get(1).enabled()).isFalse();
        assertThat(result.get(1).modelCount()).isZero();
        assertThat(result.get(1).enabledModelCount()).isZero();
    }

    private static AdminModelListQuery modelQuery(
            String keyword, String provider, String enabled, int page, int size) {
        AdminModelListQuery query = new AdminModelListQuery();
        query.setKeyword(keyword);
        query.setProvider(provider);
        query.setEnabled(enabled);
        query.setPage(page);
        query.setSize(size);
        return query;
    }

    private static PageQuery pageQuery(int page, int size) {
        PageQuery query = new PageQuery();
        query.setPage(page);
        query.setSize(size);
        return query;
    }

    private static AdminModelRow modelRow(boolean enabled, boolean providerEnabled) {
        return new AdminModelRow(
                PROVIDER, MODEL_KEY, "GPT-4o mini", 128000,
                "[\"text\",\"tool_calling\"]", "catalog", null, enabled, providerEnabled);
    }

    private static AdminPricingRow pricingRow() {
        return new AdminPricingRow(
                1L, PROVIDER, MODEL_KEY, "USD",
                new BigDecimal("0.150000"), new BigDecimal("0.600000"),
                offsetEffectiveFrom(), OffsetDateTime.parse("2026-10-01T00:00:00Z"));
    }

    private static AdminProviderRow providerRow(Boolean enabled) {
        return new AdminProviderRow(
                PROVIDER, "OpenAI", "openai-compatible", "https://api.openai.com/v1",
                enabled, 2L, 2L);
    }

    private static AdminModelPricingCreateRequest pricingRequest(String currency) {
        return new AdminModelPricingCreateRequest(
                currency, new BigDecimal("0.15"), new BigDecimal("0.60"), EFFECTIVE_FROM);
    }

    private static OffsetDateTime offsetEffectiveFrom() {
        return OffsetDateTime.parse("2026-10-01T00:00:00Z");
    }
}
