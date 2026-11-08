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

        assertThat(hardware).hasSize(28);
        Map<HardwareCategory, Long> counts = hardware.stream()
                .collect(Collectors.groupingBy(Hardware::category, Collectors.counting()));
        assertThat(counts.get(HardwareCategory.CPU)).isEqualTo(4);
        assertThat(counts.get(HardwareCategory.GPU)).isEqualTo(4);
        assertThat(counts.get(HardwareCategory.MOTHERBOARD)).isEqualTo(4);
        assertThat(counts.get(HardwareCategory.MEMORY)).isEqualTo(4);
        assertThat(counts.get(HardwareCategory.STORAGE)).isEqualTo(3);
        assertThat(counts.get(HardwareCategory.COOLER)).isEqualTo(3);
        assertThat(counts.get(HardwareCategory.CASE)).isEqualTo(3);
        assertThat(counts.get(HardwareCategory.PSU)).isEqualTo(3);
        assertThat(catalog.catalogVersion()).isNotBlank();
        assertThat(hardware).allSatisfy(item -> assertThat(item.hardwareId()).isNotBlank());
    }

    @Test
    void catalog_casesShouldHaveUnknownCoolerHeight() {
        // fixture 明确未提供机箱限高，不能据此推断为 PASS。
        assertThat(catalog.findAll()).filteredOn(item -> item.category() == HardwareCategory.CASE)
                .allSatisfy(item -> assertThat(item.specifications().maxCoolerHeightMm()).isNull());
    }

    @Test
    void catalog_findByIdShouldReturnEmptyForUnknown() {
        assertThat(catalog.findById("cpu-amd-ryzen-7-9800x3d")).isPresent();
        assertThat(catalog.findById("not-exists")).isEmpty();
    }

    @Test
    void benchmarks_shouldMapEightCpuAndGpuEntries() {
        List<Benchmark> entries = benchmarks.findAll();

        assertThat(entries).hasSize(8);
        assertThat(entries).allSatisfy(entry -> {
            assertThat(entry.hardwareId()).isNotBlank();
            assertThat(entry.benchmarkType()).isNotBlank();
            assertThat(entry.score()).isPositive();
        });
        assertThat(benchmarks.findByHardwareId("gpu-geforce-rtx-5070-ti-16gb")).isPresent();
        assertThat(benchmarks.findByHardwareId("cpu-amd-ryzen-7-9800x3d")).isPresent();
        assertThat(benchmarks.findByHardwareId("not-exists")).isEmpty();
    }

    @Test
    void offers_shouldKeepVerifiedAndMockSourcesDistinct() {
        List<Offer> entries = offers.findAll();

        assertThat(entries).hasSize(28);
        assertThat(offers.dataStatus()).isEqualTo("MIXED_DEMO");
        assertThat(offers.priceUnit()).isEqualTo("CNY_FEN");
        assertThat(entries).allSatisfy(offer -> assertThat(offer.priceFen()).isPositive());
        assertThat(entries.stream().filter(Offer::isVerifiedPrice)).hasSize(10);
        assertThat(entries.stream().filter(offer -> !offer.isVerifiedPrice())).hasSize(18);
        // 演示价必须仍可被识别，不能被当成核验价。
        assertThat(entries).filteredOn(offer -> "MOCK_DEMO".equals(offer.priceSource()))
                .allSatisfy(offer -> assertThat(offer.isVerifiedPrice()).isFalse());
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
