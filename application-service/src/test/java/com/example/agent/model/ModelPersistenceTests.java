package com.example.agent.model;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.agent.model.application.ModelCatalogService;
import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.model.domain.ProviderSummary;
import com.example.agent.model.domain.ResolvedModel;
import com.example.agent.model.infrastructure.QuotaMapper;
import com.example.agent.model.infrastructure.QuotaRow;
import com.example.agent.model.infrastructure.RuntimeTaskMapper;
import com.example.agent.model.infrastructure.RuntimeTaskRow;
import com.example.agent.model.infrastructure.UsageMapper;
import com.example.agent.model.infrastructure.UsageRecordRow;
import com.example.agent.shared.error.BusinessException;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

/**
 * V7–V10 迁移与模型仓储的持久层测试。
 *
 * <p>并发扣减、UTC 日界与 {@code invocation_id} 幂等都依赖 PostgreSQL 的行锁、
 * 唯一索引与 {@code ON CONFLICT} 语义，无法用内存数据库等价验证。</p>
 */
@SpringBootTest(properties = {
        "spring.flyway.enabled=true",
        "app.model.runtime-enabled=true",
        "app.model.internal-auth.client-secret=test-only-internal-secret"
})
@ActiveProfiles("test")
@Testcontainers
class ModelPersistenceTests {

    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:18-alpine");

    @DynamicPropertySource
    static void registerDatasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }

    private static final int CONCURRENT_REQUESTS = 16;

    private static final int DAILY_LIMIT = 5;

    private final QuotaMapper quotaMapper;

    private final RuntimeTaskMapper runtimeTaskMapper;

    private final UsageMapper usageMapper;

    private final ModelCatalogService modelCatalogService;

    @Autowired
    ModelPersistenceTests(QuotaMapper quotaMapper,
            RuntimeTaskMapper runtimeTaskMapper,
            UsageMapper usageMapper,
            ModelCatalogService modelCatalogService) {
        this.quotaMapper = quotaMapper;
        this.runtimeTaskMapper = runtimeTaskMapper;
        this.usageMapper = usageMapper;
        this.modelCatalogService = modelCatalogService;
    }

    @Test
    void listAvailable_shouldReturnSeedModelsWithCapabilities() {
        List<ResolvedModel> models = modelCatalogService.listAvailable();

        // V17 修正 DeepSeek 目录；V21 停用 OpenAI 模型（当前只提供 DeepSeek 密钥）
        assertThat(models).extracting(ResolvedModel::reference)
                .contains("deepseek:deepseek-v4-pro", "deepseek:deepseek-flash")
                .doesNotContain("deepseek:deepseek-chat", "openai:gpt-4o-mini", "openai:gpt-4o");
        ResolvedModel flash = models.stream()
                .filter(model -> "deepseek:deepseek-flash".equals(model.reference()))
                .findFirst()
                .orElseThrow();
        assertThat(flash.capabilities()).contains("text", "tool_calling");
    }

    @Test
    void listProviders_shouldMapEnabledProvidersWithModelCount() {
        List<ProviderSummary> providers = modelCatalogService.listProviders();

        // COUNT() 是包装类型 Long，record 构造参数是原始 long；结果映射必须能正确实例化
        assertThat(providers).extracting(ProviderSummary::code)
                .contains("deepseek", "qwen", "volcengine", "gemini", "anthropic");
        ProviderSummary anthropic = providers.stream()
                .filter(provider -> "anthropic".equals(provider.code()))
                .findFirst()
                .orElseThrow();
        assertThat(anthropic.protocol()).isEqualTo("anthropic-messages");
        assertThat(anthropic.modelCount()).isEqualTo(2);
    }

    @Test
    void requireAvailable_shouldRejectUnknownModel() {
        assertThatThrownBy(() -> modelCatalogService.requireAvailable("openai:missing"))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.MODEL_NOT_AVAILABLE));
    }

    @Test
    void requireAvailable_shouldRejectMalformedReference() {
        assertThatThrownBy(() -> modelCatalogService.requireAvailable("gpt-4o-mini"))
                .isInstanceOfSatisfying(BusinessException.class,
                        ex -> assertThat(ex.getErrorCode()).isEqualTo(ModelErrorCode.MODEL_REFERENCE_INVALID));
    }

    @Test
    void tryConsume_shouldNotOversellUnderConcurrency() throws Exception {
        UUID userId = UUID.randomUUID();
        LocalDate quotaDate = LocalDate.of(2026, 10, 30);
        ExecutorService executor = Executors.newFixedThreadPool(8);
        CountDownLatch startGate = new CountDownLatch(1);
        CountDownLatch doneGate = new CountDownLatch(CONCURRENT_REQUESTS);
        AtomicInteger consumed = new AtomicInteger();

        try {
            for (int index = 0; index < CONCURRENT_REQUESTS; index++) {
                executor.submit(() -> {
                    try {
                        startGate.await();
                        if (quotaMapper.tryConsume(userId, quotaDate, DAILY_LIMIT) != null) {
                            consumed.incrementAndGet();
                        }
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    } finally {
                        doneGate.countDown();
                    }
                });
            }
            startGate.countDown();
            assertThat(doneGate.await(30, TimeUnit.SECONDS)).isTrue();
        } finally {
            executor.shutdownNow();
        }

        assertThat(consumed.get()).isEqualTo(DAILY_LIMIT);
        QuotaRow row = quotaMapper.find(userId, quotaDate);
        assertThat(row).isNotNull();
        assertThat(row.usedCount()).isEqualTo(DAILY_LIMIT);
        assertThat(row.limitCount()).isEqualTo(DAILY_LIMIT);
    }

    @Test
    void tryConsume_shouldTrackQuotaPerUtcDate() {
        UUID userId = UUID.randomUUID();
        LocalDate firstDay = LocalDate.of(2026, 10, 30);
        LocalDate secondDay = firstDay.plusDays(1);

        quotaMapper.tryConsume(userId, firstDay, 10);
        quotaMapper.tryConsume(userId, firstDay, 10);
        quotaMapper.tryConsume(userId, secondDay, 10);

        QuotaRow firstDayRow = quotaMapper.find(userId, firstDay);
        QuotaRow secondDayRow = quotaMapper.find(userId, secondDay);
        assertThat(firstDayRow.usedCount()).isEqualTo(2);
        assertThat(secondDayRow.usedCount()).isEqualTo(1);
        // 次日是新的当日快照，不受首日已用影响
        assertThat(secondDayRow.limitCount()).isEqualTo(10);
    }

    @Test
    void insert_shouldIgnoreDuplicateIdempotencyKey() {
        UUID userId = UUID.randomUUID();
        OffsetDateTime now = OffsetDateTime.now();
        RuntimeTaskRow first = new RuntimeTaskRow(
                UUID.randomUUID(), userId, "t-1", null, "openai:gpt-4o-mini", "MANAGED", null, null,
                "ACTIVE", now.plusMinutes(10), now, "idem-key-1");
        RuntimeTaskRow second = new RuntimeTaskRow(
                UUID.randomUUID(), userId, "t-2", null, "openai:gpt-4o", "MANAGED", null, null,
                "ACTIVE", now.plusMinutes(10), now, "idem-key-1");

        assertThat(runtimeTaskMapper.insert(first)).isEqualTo(1);
        // 同键第二次插入被部分唯一索引吞掉，返回 0 供上层复用既有任务
        assertThat(runtimeTaskMapper.insert(second)).isZero();

        RuntimeTaskRow found = runtimeTaskMapper.findByUserAndKey(userId, "idem-key-1");
        assertThat(found.id()).isEqualTo(first.id());
        assertThat(found.threadId()).isEqualTo("t-1");
    }

    @Test
    void markExpiredBefore_shouldOnlyTouchActiveExpiredTasks() {
        UUID userId = UUID.randomUUID();
        OffsetDateTime now = OffsetDateTime.now();
        RuntimeTaskRow expired = new RuntimeTaskRow(
                UUID.randomUUID(), userId, "t-1", null, "openai:gpt-4o-mini", "MANAGED", null, null,
                "ACTIVE", now.minusMinutes(1), now.minusMinutes(11), null);
        RuntimeTaskRow active = new RuntimeTaskRow(
                UUID.randomUUID(), userId, "t-2", null, "openai:gpt-4o-mini", "MANAGED", null, null,
                "ACTIVE", now.plusMinutes(10), now, null);
        runtimeTaskMapper.insert(expired);
        runtimeTaskMapper.insert(active);

        assertThat(runtimeTaskMapper.markExpiredBefore(now)).isEqualTo(1);
        assertThat(runtimeTaskMapper.findById(expired.id()).status()).isEqualTo("EXPIRED");
        assertThat(runtimeTaskMapper.findById(active.id()).status()).isEqualTo("ACTIVE");
    }

    @Test
    void insertIgnoreDuplicates_shouldInsertInvocationOnlyOnce() {
        UUID userId = UUID.randomUUID();
        RuntimeTaskRow task = new RuntimeTaskRow(
                UUID.randomUUID(), userId, "t-1", null, "openai:gpt-4o-mini", "MANAGED", null, null,
                "ACTIVE", OffsetDateTime.now().plusMinutes(10), OffsetDateTime.now(), null);
        runtimeTaskMapper.insert(task);

        UUID invocationId = UUID.randomUUID();
        UsageRecordRow row = usageRow(invocationId, task, userId);

        int firstInsert = usageMapper.insertIgnoreDuplicates(List.of(row));
        int secondInsert = usageMapper.insertIgnoreDuplicates(List.of(row));

        assertThat(firstInsert).isEqualTo(1);
        assertThat(secondInsert).isZero();
    }

    @Test
    void insertIgnoreDuplicates_shouldSkipDuplicateInsideSameBatch() {
        UUID userId = UUID.randomUUID();
        RuntimeTaskRow task = new RuntimeTaskRow(
                UUID.randomUUID(), userId, "t-1", null, "openai:gpt-4o-mini", "MANAGED", null, null,
                "ACTIVE", OffsetDateTime.now().plusMinutes(10), OffsetDateTime.now(), null);
        runtimeTaskMapper.insert(task);

        UUID invocationId = UUID.randomUUID();
        UsageRecordRow row = usageRow(invocationId, task, userId);
        List<UsageRecordRow> batch = new ArrayList<>(List.of(row, row));

        assertThat(usageMapper.insertIgnoreDuplicates(batch)).isEqualTo(1);
    }

    private UsageRecordRow usageRow(UUID invocationId, RuntimeTaskRow task, UUID userId) {
        return new UsageRecordRow(
                invocationId, task.id(), userId, task.threadId(), "conversation", "openai", "gpt-4o-mini",
                "MANAGED", 120, 30, 850, "failure", "upstream_error", null,
                "UNKNOWN", "PLATFORM", null, OffsetDateTime.parse("2026-10-30T08:00:05Z"));
    }
}
