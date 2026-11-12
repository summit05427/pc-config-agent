package com.example.agent.pcbuild;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.agent.pcbuild.application.BuildSolver;
import com.example.agent.pcbuild.application.CompatibilityValidator;
import com.example.agent.pcbuild.domain.Benchmark;
import com.example.agent.pcbuild.domain.BuildDraft;
import com.example.agent.pcbuild.domain.BuildExplanations;
import com.example.agent.pcbuild.domain.BuildRequirements;
import com.example.agent.pcbuild.domain.BuildResult;
import com.example.agent.pcbuild.domain.BuildScenario;
import com.example.agent.pcbuild.domain.CompatibilityRule;
import com.example.agent.pcbuild.domain.CompatibilityStatus;
import com.example.agent.pcbuild.domain.ComponentRationale;
import com.example.agent.pcbuild.domain.Hardware;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.HardwareSpecifications;
import com.example.agent.pcbuild.domain.Offer;
import com.example.agent.pcbuild.domain.Preference;
import com.example.agent.pcbuild.domain.RenderMode;
import com.example.agent.pcbuild.domain.ScoringPolicyVersion;
import com.example.agent.pcbuild.domain.SolveFailureReason;
import com.example.agent.pcbuild.domain.SolveOutcome;
import com.example.agent.pcbuild.domain.WorkloadProfile;
import com.example.agent.pcbuild.infrastructure.JsonBenchmarkRepository;
import com.example.agent.pcbuild.infrastructure.JsonHardwareCatalogRepository;
import com.example.agent.pcbuild.infrastructure.JsonOfferRepository;
import java.lang.reflect.Method;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/**
 * 求解器测试：预算边界、确定性、无解原因与硬约束不放宽。
 */
class BuildSolverTests {

    private static final ObjectMapper OBJECT_MAPPER = JsonMapper.builder().build();

    private static final long GENEROUS_BUDGET_FEN = 2_000_000L;

    // 刻意取低于任何完整八件套的金额，只验证预算剪枝，不绑定具体最低价。
    private static final long TIGHT_BUDGET_FEN = 100_000L;

    // 容量过滤用例只关心「下限是否生效」；价格数据修正后大容量内存与显卡更接近真实市价，
    // 30,000 元已不足以覆盖完整八件套，这里放宽到不会触发预算剪枝的水平。
    private static final long CAPACITY_TEST_BUDGET_FEN = 6_000_000L;

    private final JsonHardwareCatalogRepository catalog =
            new JsonHardwareCatalogRepository(OBJECT_MAPPER);

    private final JsonBenchmarkRepository benchmarks =
            new JsonBenchmarkRepository(OBJECT_MAPPER);

    private final JsonOfferRepository offers = new JsonOfferRepository(OBJECT_MAPPER);

    private final BuildSolver solver = new BuildSolver(new CompatibilityValidator());

    @Test
    void solveWithinBudget_shouldReturnCompleteDeterministicBuild() {
        BuildRequirements requirements = new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.GAMING, null, null, false);

        SolveOutcome first = solve(requirements);
        SolveOutcome second = solve(requirements);

        assertThat(first.isSolved()).isTrue();
        BuildDraft build = first.build();
        assertThat(build.selection().isComplete()).isTrue();
        assertThat(build.selection().asMap()).hasSize(8);
        assertThat(build.totalPriceFen()).isPositive().isLessThanOrEqualTo(GENEROUS_BUDGET_FEN);
        assertThat(build.compatibilityReport().hasFailure()).isFalse();
        assertThat(build.offers()).hasSize(8);
        assertThat(build.offers().values()).allSatisfy(offer ->
                assertThat(offer.priceSource()).isNotBlank());
        // 相同输入必须得到完全相同的组件序列。
        assertThat(second.build().selection().idSignature())
                .isEqualTo(build.selection().idSignature());
        assertThat(second.build().totalPriceFen()).isEqualTo(build.totalPriceFen());
    }

    @Test
    void budgetShouldBeRespectedAsHardLimit() {
        SolveOutcome outcome = solve(new BuildRequirements(
                TIGHT_BUDGET_FEN, BuildScenario.BALANCED, null, null, false));

        assertThat(outcome.isSolved()).isFalse();
        assertThat(outcome.failure().reason()).isEqualTo(SolveFailureReason.BUDGET_EXCEEDED);
        assertThat(outcome.failure().minimumRequiredBudgetFen())
                .isNotNull()
                .isGreaterThan(TIGHT_BUDGET_FEN);
        // 无解时不返回任何超预算方案。
        assertThat(outcome.build()).isNull();

        long minimum = outcome.failure().minimumRequiredBudgetFen();
        SolveOutcome exact = solve(new BuildRequirements(
                minimum, BuildScenario.BALANCED, null, null, false));
        assertThat(exact.isSolved()).isTrue();
        assertThat(exact.build().totalPriceFen()).isLessThanOrEqualTo(minimum);

        SolveOutcome below = solve(new BuildRequirements(
                minimum - 1, BuildScenario.BALANCED, null, null, false));
        assertThat(below.isSolved()).isFalse();
        assertThat(below.failure().reason()).isEqualTo(SolveFailureReason.BUDGET_EXCEEDED);
        assertThat(below.failure().minimumRequiredBudgetFen()).isEqualTo(minimum);
    }

    @Test
    void midRangeBudget_shouldKeepCheapCandidatesInPool() {
        // 真实价格修正后，性能前 12 的 CPU/GPU 任意组合都超过 8000 元；
        // 若候选池只按性能截断，中端预算会被误判为无解（回归：最低可行总价曾报 31,941 元）。
        long midRangeBudgetFen = 800_000L;

        SolveOutcome outcome = solve(new BuildRequirements(
                midRangeBudgetFen, BuildScenario.GAMING, null, null, false));

        assertThat(outcome.isSolved()).isTrue();
        BuildDraft build = outcome.build();
        assertThat(build.selection().isComplete()).isTrue();
        assertThat(build.totalPriceFen()).isLessThanOrEqualTo(midRangeBudgetFen);
        assertThat(build.compatibilityReport().hasFailure()).isFalse();
    }

    @Test
    void withoutBudget_shouldUseValueStrategy() {
        SolveOutcome outcome = solve(new BuildRequirements(
                null, BuildScenario.CREATIVE, null, null, false));

        assertThat(outcome.isSolved()).isTrue();
        assertThat(outcome.build().requirements().hasBudget()).isFalse();
        assertThat(outcome.build().selection().isComplete()).isTrue();
        assertThat(outcome.build().totalPriceFen()).isPositive();
    }

    @Test
    void requireVerifiedOffers_shouldReportMissingCategoriesInsteadOfUsingMockPrices() {
        SolveOutcome outcome = solve(new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.GAMING, null, null, true));

        assertThat(outcome.isSolved()).isFalse();
        assertThat(outcome.failure().reason()).isEqualTo(SolveFailureReason.NO_CANDIDATES);
        assertThat(outcome.failure().missingCategories())
                .contains("MEMORY", "STORAGE", "COOLER", "CASE", "PSU");
        assertThat(outcome.failure().candidateCounts().get("MEMORY")).isZero();
    }

    @Test
    void minMemoryRequirement_shouldFilterCandidates() {
        SolveOutcome outcome = solve(new BuildRequirements(
                CAPACITY_TEST_BUDGET_FEN, BuildScenario.CREATIVE, 64, null, false));

        assertThat(outcome.isSolved()).isTrue();
        // 满足下限即可，更高容量更便宜时也可以被选中，不绑定具体容量。
        assertThat(outcome.build().selection().memory().specifications().capacityGb())
                .isGreaterThanOrEqualTo(64);
    }

    @Test
    void minStorageRequirement_shouldFilterCandidates() {
        SolveOutcome outcome = solve(new BuildRequirements(
                CAPACITY_TEST_BUDGET_FEN, BuildScenario.CREATIVE, null, 2048, false));

        assertThat(outcome.isSolved()).isTrue();
        // 目录里可能存在多条 ≥2048GB 的存储，断言「满足下限」而非绑定某条具体容量。
        assertThat(outcome.build().selection().storage().specifications().capacityGb())
                .isGreaterThanOrEqualTo(2048);
    }

    @Test
    void unknownCoolerHeight_shouldDefaultToPass() {
        SolveOutcome outcome = solve(new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.OFFICE, null, null, false));

        assertThat(outcome.isSolved()).isTrue();
        CompatibilityStatus coolerHeight = outcome.build().compatibilityReport().checks().stream()
                .filter(check -> check.ruleId().equals(CompatibilityRule.COOLER_CASE_HEIGHT.ruleId()))
                .findFirst()
                .orElseThrow()
                .status();
        // 机箱限高缺失时按产品策略默认通过，整体报告不应因它变成 UNKNOWN
        assertThat(coolerHeight).isEqualTo(CompatibilityStatus.PASS);
        assertThat(outcome.build().compatibilityReport().overallStatus())
                .isNotEqualTo(CompatibilityStatus.UNKNOWN);
    }

    @Test
    void selectedBuildShouldHaveOneOfferPerCategory() {
        SolveOutcome outcome = solve(new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.BALANCED, null, null, false));

        assertThat(outcome.isSolved()).isTrue();
        List<HardwareCategory> categories = outcome.build().offers().keySet().stream().toList();
        assertThat(categories).containsExactlyInAnyOrder(
                HardwareCategory.CPU,
                HardwareCategory.MOTHERBOARD,
                HardwareCategory.MEMORY,
                HardwareCategory.GPU,
                HardwareCategory.PSU,
                HardwareCategory.CASE,
                HardwareCategory.COOLER,
                HardwareCategory.STORAGE);
    }

    @Test
    void generalProfile_shouldKeepLegacyBalancedBehaviour() {
        BuildRequirements requirements = new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.BALANCED, null, null, false);

        assertThat(requirements.workloadProfile()).isEqualTo(WorkloadProfile.GENERAL);
        assertThat(requirements.scenario()).isEqualTo(BuildScenario.BALANCED);
        assertThat(requirements.renderMode()).isEqualTo(RenderMode.BOTH);
        assertThat(requirements.scoringVersion()).isEqualTo(ScoringPolicyVersion.SCORING_VERSION);

        SolveOutcome first = solve(requirements);
        SolveOutcome second = solve(requirements);

        assertThat(first.isSolved()).isTrue();
        assertThat(second.build().selection().idSignature())
                .isEqualTo(first.build().selection().idSignature());
        assertThat(second.build().totalPriceFen()).isEqualTo(first.build().totalPriceFen());
    }

    @Test
    void aiInference_shouldPreferHighVramGpu() {
        Hardware gpu24Gb = synthetic(
                "gpu-test-24gb", HardwareCategory.GPU, "{\"chipset\":\"test\",\"vram_gb\":24}");
        List<Hardware> hardware = new ArrayList<>(catalog.findAll());
        hardware.add(gpu24Gb);
        List<Offer> offerList = new ArrayList<>(offers.findAll());
        offerList.add(offer(gpu24Gb, 900_000L));

        SolveOutcome outcome = solver.solve(
                new BuildRequirements(GENEROUS_BUDGET_FEN, BuildScenario.AI_INFERENCE, null, null, false),
                hardware,
                offerList,
                benchmarks.findAll(),
                catalog.catalogVersion(),
                offers.dataStatus(),
                LocalDate.now());

        assertThat(outcome.isSolved()).isTrue();
        assertThat(outcome.build().requirements().workloadProfile())
                .isEqualTo(WorkloadProfile.AI_INFERENCE);
        assertThat(outcome.build().selection().gpu().hardwareId()).isEqualTo("gpu-test-24gb");
    }

    @Test
    void aiInference_shouldKeepHighestVramCandidatesInGpuPool() {
        // 13 张 24GB 卡超过 12 的候选上限，VRAM_FIRST 排序必须把 16GB 的真实卡挤出候选池。
        List<Hardware> hardware = new ArrayList<>(catalog.findAll());
        List<Offer> offerList = new ArrayList<>(offers.findAll());
        for (int index = 0; index < 13; index++) {
            Hardware gpu = synthetic(
                    "gpu-test-vram-" + index, HardwareCategory.GPU,
                    "{\"chipset\":\"test\",\"vram_gb\":24}");
            hardware.add(gpu);
            offerList.add(offer(gpu, 900_000L + index));
        }

        SolveOutcome outcome = solver.solve(
                new BuildRequirements(GENEROUS_BUDGET_FEN, BuildScenario.AI_INFERENCE, null, null, false),
                hardware,
                offerList,
                benchmarks.findAll(),
                catalog.catalogVersion(),
                offers.dataStatus(),
                LocalDate.now());

        assertThat(outcome.isSolved()).isTrue();
        assertThat(outcome.build().selection().gpu().hardwareId()).startsWith("gpu-test-vram-");
    }

    @Test
    void programming_shouldKeepMulticoreCandidatesInCpuPool() {
        // 用 13 颗 synthetic 24 核 CPU 填满 CPU 池，让 MULTICORE_FIRST 排序
        // 保持全部 synthetic 在 PERFORMANCE_LIMIT 里，求解器必须选中其中一颗，
        // 否则说明 PERFORMANCE_LIMIT 排序失效或 CHEAP 档错误挤出了多核候选。
        final String syntheticSocket = "AM5";  // 兼容真实 AM5 主板
        List<Hardware> hardware = new ArrayList<>();
        List<Offer> offerList = new ArrayList<>();

        // 只保留真实非 CPU 硬件，CPU 全部换成 synthetic 24 核
        for (Hardware h : catalog.findAll()) {
            if (h.category() != HardwareCategory.CPU) {
                hardware.add(h);
                offerList.addAll(offers.findAll().stream()
                        .filter(o -> o.hardwareId().equals(h.hardwareId()))
                        .toList());
            }
        }
        for (int index = 0; index < 13; index++) {
            Hardware cpu = synthetic(
                    "cpu-test-multicore-" + index, HardwareCategory.CPU,
                    "{\"socket\":\"" + syntheticSocket + "\",\"core_count\":24,\"thread_count\":48,\"tdp_w\":120}");
            hardware.add(cpu);
            offerList.add(offer(cpu, 200_000L + index));
        }

        SolveOutcome outcome = solver.solve(
                new BuildRequirements(GENEROUS_BUDGET_FEN, BuildScenario.PROGRAMMING, null, null, false),
                hardware,
                offerList,
                benchmarks.findAll(),
                catalog.catalogVersion(),
                offers.dataStatus(),
                LocalDate.now());

        assertThat(outcome.isSolved()).isTrue();
        assertThat(outcome.build().requirements().workloadProfile())
                .isEqualTo(WorkloadProfile.PROGRAMMING);
        // CPU 池里全是 synthetic 24 核，且 MULTICORE_FIRST 保证它们全在候选池里
        assertThat(outcome.build().selection().cpu().specifications().coreCount())
                .isGreaterThanOrEqualTo(24);
    }

    @Test
    void renderingProfile_shouldUseDifferentWeightsForCpuAndGpuRenderMode() {
        BuildRequirements cpuRendering = new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.WORKSTATION, null, null, false,
                WorkloadProfile.RENDERING, RenderMode.CPU, null);
        BuildRequirements gpuRendering = new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.WORKSTATION, null, null, false,
                WorkloadProfile.RENDERING, RenderMode.GPU, null);

        assertThat(cpuRendering.scenario()).isEqualTo(BuildScenario.PROGRAMMING);
        assertThat(gpuRendering.scenario()).isEqualTo(BuildScenario.GAMING);
        assertThat(cpuRendering.scenario().cpuWeight())
                .isNotEqualTo(gpuRendering.scenario().cpuWeight());
        assertThat(solve(cpuRendering).isSolved()).isTrue();
        assertThat(solve(gpuRendering).isSolved()).isTrue();
    }

    @Test
    void valuePreference_shouldChooseHigherValueCombinationWithinBudget() {
        Hardware valueGpu = synthetic(
                "gpu-test-value", HardwareCategory.GPU,
                "{\"chipset\":\"test\",\"vram_gb\":8,\"length_mm\":200,\"tdp_w\":180}");
        Hardware performanceGpu = synthetic(
                "gpu-test-perf", HardwareCategory.GPU,
                "{\"chipset\":\"test\",\"vram_gb\":8,\"length_mm\":200,\"tdp_w\":180}");
        List<Hardware> hardware = new ArrayList<>(catalog.findAll());
        hardware.add(valueGpu);
        hardware.add(performanceGpu);
        List<Offer> offerList = new ArrayList<>(offers.findAll());
        // 价格刻意低于任何真实显卡，保证「性价比优先」的选择不受运行时报价变化影响。
        offerList.add(offer(valueGpu, 50_000L));
        offerList.add(offer(performanceGpu, 900_000L));
        List<Benchmark> benchmarkList = new ArrayList<>(benchmarks.findAll());
        benchmarkList.add(gpuBenchmark("gpu-test-value", 30_000.0));
        benchmarkList.add(gpuBenchmark("gpu-test-perf", 60_000.0));

        BuildRequirements valueRequirements = new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.GAMING, null, null, false,
                null, null, null, Preference.VALUE);
        BuildRequirements performanceRequirements = new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.GAMING, null, null, false,
                null, null, null, Preference.PERFORMANCE);

        SolveOutcome value = solver.solve(valueRequirements, hardware, offerList, benchmarkList,
                catalog.catalogVersion(), offers.dataStatus(), LocalDate.now());
        SolveOutcome performance = solver.solve(performanceRequirements, hardware, offerList,
                benchmarkList, catalog.catalogVersion(), offers.dataStatus(), LocalDate.now());

        assertThat(value.isSolved()).isTrue();
        assertThat(performance.isSolved()).isTrue();
        // 性能优先选高跑分卡，性价比优先选「分数/价格」更高的低跑分卡。
        assertThat(performance.build().selection().gpu().hardwareId()).isEqualTo("gpu-test-perf");
        assertThat(value.build().selection().gpu().hardwareId()).isEqualTo("gpu-test-value");
        assertThat(value.build().totalPriceFen())
                .isLessThan(performance.build().totalPriceFen());
        assertThat(BuildExplanations.reasonSummary(valueRequirements)).contains("性价比优先");
        assertThat(BuildExplanations.reasonSummary(performanceRequirements))
                .contains("性能总分优先");
    }

    @Test
    void performancePreference_shouldMatchUnspecifiedPreference() {
        BuildRequirements performance = new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.GAMING, null, null, false,
                null, null, null, Preference.PERFORMANCE);
        BuildRequirements unspecified = new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.GAMING, null, null, false);

        SolveOutcome first = solve(performance);
        SolveOutcome second = solve(unspecified);

        assertThat(first.isSolved()).isTrue();
        assertThat(second.isSolved()).isTrue();
        assertThat(first.build().selection().idSignature())
                .isEqualTo(second.build().selection().idSignature());
        assertThat(first.build().totalPriceFen()).isEqualTo(second.build().totalPriceFen());
    }

    @Test
    void cheapestMemoryTypeMismatch_shouldBeFilteredBeforeTruncation() {
        // 9 条更便宜的 DDR4 会占满按价格排序的前 8 个内存位，而主板只支持 DDR5；
        // 兼容感知池构建必须先按内存类型过滤，否则整个内存池与主板失配、求解必然无解。
        List<Hardware> hardware = new ArrayList<>();
        List<Offer> offerList = new ArrayList<>();

        Hardware cpu = synthetic("regression-cpu", HardwareCategory.CPU,
                "{\"socket\":\"AM5\",\"core_count\":8,\"thread_count\":16,\"tdp_w\":120}");
        Hardware motherboard = synthetic("regression-motherboard", HardwareCategory.MOTHERBOARD,
                "{\"socket\":\"AM5\",\"form_factor\":\"ATX\",\"memory_type\":\"DDR5\","
                        + "\"memory_slots\":4,\"m2_slot_count\":2,\"sata_ports\":0}");
        Hardware gpu = synthetic("regression-gpu", HardwareCategory.GPU,
                "{\"chipset\":\"test\",\"vram_gb\":8,\"length_mm\":250,\"tdp_w\":200,"
                        + "\"external_power\":{\"connector_type\":\"PCIE_8PIN\",\"count\":1}}");
        Hardware psu = synthetic("regression-psu", HardwareCategory.PSU,
                "{\"wattage_w\":850,\"pcie_8pin_count\":4,\"pcie_12vhpwr_count\":1}");
        Hardware pcCase = synthetic("regression-case", HardwareCategory.CASE,
                "{\"supported_mainboard_form_factors\":[\"ATX\"],\"max_gpu_length_mm\":350,"
                        + "\"max_cooler_height_mm\":170}");
        Hardware cooler = synthetic("regression-cooler", HardwareCategory.COOLER,
                "{\"supported_sockets\":[\"AM5\"],\"height_mm\":150,\"cooler_type\":\"AIR\"}");
        Hardware storage = synthetic("regression-storage", HardwareCategory.STORAGE,
                "{\"interface\":\"M.2\",\"form_factor\":\"M.2 2280\",\"capacity_gb\":1024}");
        hardware.addAll(List.of(cpu, motherboard, gpu, psu, pcCase, cooler, storage));
        offerList.add(offer(cpu, 250_000L));
        offerList.add(offer(motherboard, 220_000L));
        offerList.add(offer(gpu, 450_000L));
        offerList.add(offer(psu, 110_000L));
        offerList.add(offer(pcCase, 70_000L));
        offerList.add(offer(cooler, 55_000L));
        offerList.add(offer(storage, 90_000L));

        for (int index = 0; index < 9; index++) {
            Hardware ddr4 = synthetic("regression-memory-ddr4-" + index, HardwareCategory.MEMORY,
                    "{\"memory_type\":\"DDR4\",\"capacity_gb\":32,\"module_count\":2}");
            hardware.add(ddr4);
            offerList.add(offer(ddr4, 50_000L + index));
        }
        Hardware ddr5 = synthetic("regression-memory-ddr5", HardwareCategory.MEMORY,
                "{\"memory_type\":\"DDR5\",\"capacity_gb\":32,\"module_count\":2}");
        hardware.add(ddr5);
        offerList.add(offer(ddr5, 200_000L));

        BuildRequirements requirements = new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.BALANCED, null, null, false);
        SolveOutcome outcome = solver.solve(requirements, hardware, offerList, List.of(),
                catalog.catalogVersion(), offers.dataStatus(), LocalDate.now());

        assertThat(outcome.isSolved()).isTrue();
        assertThat(outcome.build().selection().memory().specifications().memoryType())
                .isEqualTo("DDR5");

        Map<String, Integer> candidateCounts = compatiblePoolSizes(requirements, hardware, offerList);
        assertThat(candidateCounts.get("CPU")).isBetween(1, 12);
        assertThat(candidateCounts.get("GPU")).isBetween(1, 12);
        assertThat(candidateCounts.get("MEMORY")).isBetween(1, 8);
        assertThat(candidateCounts.get("MOTHERBOARD")).isBetween(1, 8);
        assertThat(candidateCounts.get("COOLER")).isBetween(1, 8);
    }

    @Test
    void componentRationales_shouldCoverEveryCategoryWithVerifiableNumbers() {
        BuildResult result = resultOf(new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.AI_INFERENCE, null, null, false));

        assertThat(result.componentRationales()).hasSize(8);
        assertThat(result.componentRationales())
                .extracting(ComponentRationale::hardwareCategory)
                .containsExactlyElementsOf(HardwareCategory.REQUIRED_CATEGORIES);
        assertThat(result.componentRationales()).allSatisfy(rationale -> {
            assertThat(rationale.hardwareId()).isNotBlank();
            assertThat(rationale.reason()).contains("对方案总分贡献 ", "占总价 ");
            assertThat(rationale.reason()).matches(".*占总价 \\d+%.*");
            assertThat(rationale.reason())
                    .doesNotContain("FPS", "tok/s", "最强", "碾压");
        });
        String gpuReason = reasonOf(result, HardwareCategory.GPU);
        assertThat(gpuReason).contains("显存");
        assertThat(result.reasonSummary()).contains("本地 AI 推理");
    }

    @Test
    void componentRationales_shouldReflectProfileSpecificRanking() {
        BuildResult gaming = resultOf(new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.GAMING, null, null, false));
        assertThat(reasonOf(gaming, HardwareCategory.CPU)).contains("单线程");

        BuildResult programming = resultOf(new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.PROGRAMMING, null, null, false));
        assertThat(reasonOf(programming, HardwareCategory.CPU)).contains("多核");

        assertThat(BuildExplanations.reasonSummary(new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.CREATIVE, null, null, false)))
                .contains("视频剪辑");
        assertThat(BuildExplanations.reasonSummary(new BuildRequirements(
                GENEROUS_BUDGET_FEN, BuildScenario.WORKSTATION, null, null, false,
                WorkloadProfile.RENDERING, RenderMode.CPU, null)))
                .contains("CPU 渲染");
    }

    /**
     * 成功结果不暴露候选数，反射复用求解器自身的兼容感知池构建逻辑读取。
     */
    @SuppressWarnings("unchecked")
    private Map<String, Integer> compatiblePoolSizes(
            BuildRequirements requirements, List<Hardware> hardware, List<Offer> offerList) {
        try {
            Method cheapestMethod = BuildSolver.class.getDeclaredMethod(
                    "cheapestUsableOffers", List.class, LocalDate.class, boolean.class);
            cheapestMethod.setAccessible(true);
            Map<String, Offer> cheapest = (Map<String, Offer>) cheapestMethod.invoke(
                    solver, offerList, LocalDate.now(), requirements.requireVerifiedOffers());

            Method candidatesMethod = BuildSolver.class.getDeclaredMethod("candidatesOf",
                    HardwareCategory.class, List.class, Map.class, Map.class, BuildRequirements.class);
            candidatesMethod.setAccessible(true);
            Method poolsMethod = BuildSolver.class.getDeclaredMethod(
                    "buildCompatiblePools", Map.class, BuildRequirements.class, boolean.class);
            poolsMethod.setAccessible(true);

            Map<HardwareCategory, List<Object>> rawPools = new LinkedHashMap<>();
            for (HardwareCategory category : HardwareCategory.REQUIRED_CATEGORIES) {
                rawPools.put(category, (List<Object>) candidatesMethod.invoke(
                        solver, category, hardware, cheapest, new HashMap<String, Benchmark>(),
                        requirements));
            }
            Map<HardwareCategory, List<Object>> pools = (Map<HardwareCategory, List<Object>>)
                    poolsMethod.invoke(solver, rawPools, requirements, requirements.hasBudget());

            Map<String, Integer> counts = new LinkedHashMap<>();
            for (HardwareCategory category : HardwareCategory.REQUIRED_CATEGORIES) {
                counts.put(category.name(), pools.getOrDefault(category, List.of()).size());
            }
            return counts;
        } catch (ReflectiveOperationException ex) {
            throw new IllegalStateException("无法读取候选池大小", ex);
        }
    }

    private SolveOutcome solve(BuildRequirements requirements) {
        return solver.solve(
                requirements,
                catalog.findAll(),
                offers.findAll(),
                benchmarks.findAll(),
                catalog.catalogVersion(),
                offers.dataStatus(),
                LocalDate.now());
    }

    private BuildResult resultOf(BuildRequirements requirements) {
        SolveOutcome outcome = solve(requirements);
        assertThat(outcome.isSolved()).isTrue();
        return BuildResult.fromDraft(
                UUID.randomUUID(), UUID.randomUUID(), outcome.build(), Instant.now());
    }

    private String reasonOf(BuildResult result, HardwareCategory category) {
        return result.componentRationales().stream()
                .filter(rationale -> rationale.hardwareCategory() == category)
                .findFirst()
                .orElseThrow()
                .reason();
    }

    private Benchmark gpuBenchmark(String hardwareId, double score) {
        return new Benchmark(
                hardwareId, "G3D_MARK", score, 1_200.0, 1, 100,
                "TEST", 1.0, "test");
    }

    private Hardware synthetic(String hardwareId, HardwareCategory category, String specificationsJson) {
        HardwareSpecifications specifications = OBJECT_MAPPER.readValue(
                specificationsJson, HardwareSpecifications.class);
        return new Hardware(
                hardwareId, category, "test", "test", null, null, specifications,
                "PARTIAL", "CURRENT", "ELIGIBLE");
    }

    private Offer offer(Hardware hardware, long priceFen) {
        return new Offer(
                "offer-" + hardware.hardwareId(), hardware.hardwareId(), hardware.category(),
                "TEST", "test-seller", "test-shop", "test-title", "test-sku", priceFen,
                "NORMAL", "https://example.invalid", null, null,
                Offer.MATCH_MOCK, "MOCK_DEMO", null);
    }
}
