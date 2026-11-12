package com.example.agent.pcbuild;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.agent.pcbuild.domain.Benchmark;
import com.example.agent.pcbuild.domain.Hardware;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.Offer;
import com.example.agent.pcbuild.infrastructure.JsonBenchmarkRepository;
import com.example.agent.pcbuild.infrastructure.JsonHardwareCatalogRepository;
import com.example.agent.pcbuild.infrastructure.JsonOfferRepository;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/**
 * JSON fixture 仓储测试：验证数据形状、类别数量与报价来源统计。
 */
class PcFixtureRepositoryTests {

    private static final ObjectMapper OBJECT_MAPPER = JsonMapper.builder().build();

    private final JsonHardwareCatalogRepository catalog =
            new JsonHardwareCatalogRepository(OBJECT_MAPPER);

    private final JsonBenchmarkRepository benchmarks =
            new JsonBenchmarkRepository(OBJECT_MAPPER);

    private final JsonOfferRepository offers = new JsonOfferRepository(OBJECT_MAPPER);

    @Test
    void catalog_shouldExposeAllCategoriesAndStableIds() {
        List<Hardware> hardware = catalog.findAll();

        // 目录随采集持续扩充，因此只校验结构与类别覆盖，不锁定具体条数。
        assertThat(hardware).isNotEmpty();
        assertThat(hardware).allSatisfy(item -> assertThat(item.hardwareId()).isNotBlank());
        assertThat(hardware).extracting(Hardware::hardwareId).doesNotHaveDuplicates();
        Map<HardwareCategory, Long> counts = hardware.stream()
                .collect(Collectors.groupingBy(Hardware::category, Collectors.counting()));
        assertThat(counts.keySet()).containsExactlyInAnyOrder(HardwareCategory.values());
        assertThat(counts.values()).allSatisfy(count -> assertThat(count).isPositive());
        assertThat(counts.values().stream().mapToLong(Long::longValue).sum()).isEqualTo(hardware.size());
        assertThat(catalog.catalogVersion()).isNotBlank();
    }

    @Test
    void catalog_caseCoolerHeightIsMeasuredOrUnknown() {
        // 机箱限高：国行型号带实测值，海外 fixture 未采集则为 null；不允许出现 0 或负数这类占位值
        assertThat(catalog.findAll()).filteredOn(item -> item.category() == HardwareCategory.CASE)
                .allSatisfy(item -> {
                    Integer height = item.specifications().maxCoolerHeightMm();
                    if (height != null) {
                        assertThat(height).isPositive();
                    }
                });
    }

    @Test
    void catalog_shouldReadImageUrlFromSourceNode() {
        // 图片挂在 source.image_url 下，只有采集到图片的条目才有值
        assertThat(catalog.findById("cpu-amd-ryzen-5-9600x"))
                .get()
                .extracting(Hardware::imageUrl)
                .asString()
                .startsWith("https://");

        // 未采集图片的条目必须保持 null，不能用占位图冒充（国行补充型号暂未采集图片）
        assertThat(catalog.findById("gpu-galax-sacred-blade-rtx-5060-ti-16gb"))
                .get()
                .extracting(Hardware::imageUrl)
                .isNull();
    }

    @Test
    void catalog_findByIdShouldReturnEmptyForUnknown() {
        assertThat(catalog.findById("cpu-amd-ryzen-7-9800x3d")).isPresent();
        assertThat(catalog.findById("not-exists")).isEmpty();
    }

    @Test
    void benchmarks_shouldMapCpuAndGpuEntries() {
        List<Benchmark> entries = benchmarks.findAll();

        // 跑分条数随 PassMark 匹配结果变化，不再固定条数，只校验字段完整性与关键型号覆盖。
        assertThat(entries).isNotEmpty();
        assertThat(entries).allSatisfy(entry -> {
            assertThat(entry.hardwareId()).isNotBlank();
            assertThat(entry.benchmarkType()).isNotBlank();
            assertThat(entry.score()).isPositive();
        });
        assertThat(benchmarks.findByHardwareId("gpu-geforce-rtx-5070-ti-16gb-563955")).isPresent();
        assertThat(benchmarks.findByHardwareId("cpu-amd-ryzen-7-9800x3d")).isPresent();
        assertThat(benchmarks.findByHardwareId("not-exists")).isEmpty();
    }

    @Test
    void offers_shouldCarryPlatformObservedStatusAndNoOwnerVerified() {
        List<Offer> entries = offers.findAll();

        // 本轮 offers 全部来自 Stage 4 短名单的 WebSearch/估算价，尚未有人工逐件核验。
        assertThat(entries).isNotEmpty();
        assertThat(offers.dataStatus()).isEqualTo("PLATFORM_OBSERVED_ONLY");
        assertThat(offers.priceUnit()).isEqualTo("CNY_FEN");
        assertThat(entries).allSatisfy(offer -> assertThat(offer.priceFen()).isPositive());
        // 全量 PLATFORM_OBSERVED，无 OWNER_VERIFIED 也无 MOCK_DEMO。
        long verifiedCount = entries.stream().filter(Offer::isVerifiedPrice).count();
        assertThat(verifiedCount).isEqualTo(0L);
        assertThat(entries).allSatisfy(offer -> assertThat(offer.priceSource())
                .isEqualTo("PLATFORM_OBSERVED"));
    }

    @Test
    void offers_shouldAllBeUsableForSolverToday() {
        LocalDate today = LocalDate.now();

        assertThat(offers.findAll()).allSatisfy(offer ->
                assertThat(offer.isUsableOn(today)).isTrue());
        assertThat(offers.findByHardwareId("cpu-amd-ryzen-7-9800x3d")).hasSize(1);
        assertThat(offers.findByHardwareId("not-exists")).isEmpty();
    }
}
