package com.example.agent.pcbuild;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.agent.pcbuild.application.BuildSolver;
import com.example.agent.pcbuild.application.CompatibilityValidator;
import com.example.agent.pcbuild.domain.Benchmark;
import com.example.agent.pcbuild.domain.BuildRequirements;
import com.example.agent.pcbuild.domain.BuildScenario;
import com.example.agent.pcbuild.domain.BuildSolverVersion;
import com.example.agent.pcbuild.domain.CompatibilityCheck;
import com.example.agent.pcbuild.domain.CompatibilityReport;
import com.example.agent.pcbuild.domain.CompatibilityRule;
import com.example.agent.pcbuild.domain.Hardware;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.HardwareSelection;
import com.example.agent.pcbuild.domain.HardwareSpecifications;
import com.example.agent.pcbuild.domain.Offer;
import com.example.agent.pcbuild.domain.SolveOutcome;
import com.example.agent.pcbuild.infrastructure.JsonBenchmarkRepository;
import com.example.agent.pcbuild.infrastructure.JsonHardwareCatalogRepository;
import com.example.agent.pcbuild.infrastructure.JsonOfferRepository;
import java.lang.reflect.Method;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/**
 * Stage 10 §9.4 求解性能基线。
 *
 * <p>不启动 Spring、Testcontainers 或数据库，直接以内存数据集驱动 {@link BuildSolver}。
 * 场景 A/B 使用运行时 {@code pc-config} 目录，场景 C/D 使用每类 200 条的合成候选池，
 * 用于观察候选上限（CPU/GPU 12、其余 8）之外的搜索成本。</p>
 *
 * <p>断言只覆盖确定性的候选数与评估组合数，不对耗时做断言，避免 CI 因机器抖动失败。
 * 成功结果不暴露候选数，因此通过反射复用求解器自身的候选池构建方法读取，不修改生产代码。</p>
 *
 * <p><b>口径说明：</b>候选池由 {@code buildCompatiblePools} 先按 CPU 插槽与主板内存类型过滤、
 * 再按画像排序截断，因此本基准度量的是「兼容感知池构建 + DFS 搜索」的总成本，
 * 不是纯 DFS 成本；对比历史数据时必须带上这一前提。</p>
 */
class BuildSolverBenchmarkTests {

    private static final ObjectMapper OBJECT_MAPPER = JsonMapper.builder().build();

    /** 固定询价日期，保证报价有效期判断不随运行日期漂移。 */
    private static final LocalDate PRICING_DATE = LocalDate.of(2026, 11, 9);

    private static final int WARMUP_ITERATIONS = 10;

    private static final int MEASUREMENT_ITERATIONS = 20;

    private static final int SYNTHETIC_PER_CATEGORY = 200;

    private static final long SCENE_A_BUDGET_FEN = 1_500_000L;

    private static final long SYNTHETIC_BUDGET_FEN = 2_000_000L;

    private static final int CPU_GPU_CANDIDATE_LIMIT = 12;

    private static final int COMPONENT_CANDIDATE_LIMIT = 8;

    private final JsonHardwareCatalogRepository catalog =
            new JsonHardwareCatalogRepository(OBJECT_MAPPER);

    private final JsonOfferRepository offers = new JsonOfferRepository(OBJECT_MAPPER);

    private final JsonBenchmarkRepository benchmarks = new JsonBenchmarkRepository(OBJECT_MAPPER);

    @Test
    void sceneA_runtimeCatalogGamingBudget() {
        report("A", new BuildRequirements(SCENE_A_BUDGET_FEN, BuildScenario.GAMING, null, null, false),
                catalog.findAll(), offers.findAll(), benchmarks.findAll(),
                "runtime pc-config, GAMING, 15000 CNY");
    }

    @Test
    void sceneB_runtimeCatalogWithoutBudget() {
        report("B", new BuildRequirements(null, BuildScenario.GAMING, null, null, false),
                catalog.findAll(), offers.findAll(), benchmarks.findAll(),
                "runtime pc-config, GAMING, no budget");
    }

    @Test
    void sceneC_syntheticCandidatePoolGeneralBudget() {
        SyntheticDataset dataset = syntheticDataset();
        int evaluated = report("C",
                new BuildRequirements(SYNTHETIC_BUDGET_FEN, BuildScenario.BALANCED, null, null, false),
                dataset.hardware(), dataset.offers(), dataset.benchmarks(),
                "synthetic 200/category, GENERAL(BALANCED), 20000 CNY");
        assertThat(evaluated).isPositive();
    }

    @Test
    void sceneD_syntheticCandidatePoolAiInferenceBudget() {
        SyntheticDataset dataset = syntheticDataset();
        int evaluated = report("D",
                new BuildRequirements(SYNTHETIC_BUDGET_FEN, BuildScenario.AI_INFERENCE, null, null, false),
                dataset.hardware(), dataset.offers(), dataset.benchmarks(),
                "synthetic 200/category, AI_INFERENCE, 20000 CNY");
        assertThat(evaluated).isPositive();
    }

    /**
     * 执行一个场景：warmup 后测量 20 次，输出一行基线。
     *
     * @return 单次求解评估到的完整组合数
     */
    private int report(
            String scenario,
            BuildRequirements requirements,
            List<Hardware> hardware,
            List<Offer> offerList,
            List<Benchmark> benchmarkList,
            String note) {

        for (int iteration = 0; iteration < WARMUP_ITERATIONS; iteration++) {
            new BuildSolver(new CountingValidator()).solve(requirements, hardware, offerList,
                    benchmarkList, catalog.catalogVersion(), offers.dataStatus(), PRICING_DATE);
        }

        long[] durationsNanos = new long[MEASUREMENT_ITERATIONS];
        SolveOutcome outcome = null;
        CountingValidator validator = null;
        for (int iteration = 0; iteration < MEASUREMENT_ITERATIONS; iteration++) {
            validator = new CountingValidator();
            BuildSolver solver = new BuildSolver(validator);
            long start = System.nanoTime();
            outcome = solver.solve(requirements, hardware, offerList, benchmarkList,
                    catalog.catalogVersion(), offers.dataStatus(), PRICING_DATE);
            durationsNanos[iteration] = System.nanoTime() - start;
        }

        Map<String, Integer> candidateCounts = candidatePoolSizes(
                new BuildSolver(new CompatibilityValidator()), requirements, hardware, offerList, benchmarkList);
        int evaluated = evaluatedCombinations(outcome, validator);
        long medianNanos = percentile(durationsNanos, 0.50);
        long p95Nanos = percentile(durationsNanos, 0.95);

        System.out.printf(Locale.ROOT,
                "[bench] scenario=%s solver=%s candidates=%s evaluatedCombinationCount=%d "
                        + "ruleCheckCalls=%d fullValidateCalls=%d medianMs=%.3f p95Ms=%.3f solved=%s note=%s%n",
                scenario, BuildSolverVersion.SOLVER_VERSION, candidateCounts, evaluated,
                validator.checkCalls, validator.validateCalls,
                medianNanos / 1_000_000.0, p95Nanos / 1_000_000.0, outcome.isSolved(), note);

        assertThat(candidateCounts).isNotEmpty();
        assertThat(evaluated).isPositive();
        return evaluated;
    }

    /**
     * 成功结果不包含候选数，通过反射复用求解器的候选池构建逻辑，避免复制一套会失同步的筛选规则。
     */
    @SuppressWarnings("unchecked")
    private Map<String, Integer> candidatePoolSizes(
            BuildSolver solver,
            BuildRequirements requirements,
            List<Hardware> hardware,
            List<Offer> offerList,
            List<Benchmark> benchmarkList) {

        try {
            Method cheapestMethod = BuildSolver.class.getDeclaredMethod(
                    "cheapestUsableOffers", List.class, LocalDate.class, boolean.class);
            cheapestMethod.setAccessible(true);
            Map<String, Offer> cheapest = (Map<String, Offer>) cheapestMethod.invoke(
                    solver, offerList, PRICING_DATE, requirements.requireVerifiedOffers());

            Map<String, Benchmark> benchmarkIndex = new HashMap<>();
            for (Benchmark benchmark : benchmarkList) {
                benchmarkIndex.put(benchmark.hardwareId(), benchmark);
            }

            Method candidatesMethod = BuildSolver.class.getDeclaredMethod("candidatesOf",
                    HardwareCategory.class, List.class, Map.class, Map.class, BuildRequirements.class);
            candidatesMethod.setAccessible(true);
            Method poolsMethod = BuildSolver.class.getDeclaredMethod(
                    "buildCompatiblePools", Map.class, BuildRequirements.class, boolean.class);
            poolsMethod.setAccessible(true);

            Map<HardwareCategory, List<Object>> rawPools = new LinkedHashMap<>();
            for (HardwareCategory category : HardwareCategory.REQUIRED_CATEGORIES) {
                rawPools.put(category, (List<Object>) candidatesMethod.invoke(
                        solver, category, hardware, cheapest, benchmarkIndex, requirements));
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

    private int evaluatedCombinations(SolveOutcome outcome, CountingValidator validator) {
        if (outcome.failure() != null) {
            return outcome.failure().evaluatedCombinationCount();
        }
        // 成功时 toDraft 会再执行一次全量校验，需要从「通过校验的全量调用数」中扣除。
        return (int) Math.max(0L, validator.successfulValidateCalls - 1L);
    }

    /** 返回排序后第 ceil(percentile * n) 个耗时。 */
    private long percentile(long[] values, double percentile) {
        long[] sorted = Arrays.copyOf(values, values.length);
        Arrays.sort(sorted);
        int index = (int) Math.ceil(percentile * sorted.length) - 1;
        return sorted[Math.max(0, Math.min(index, sorted.length - 1))];
    }

    private SyntheticDataset syntheticDataset() {
        List<Hardware> hardware = new ArrayList<>();
        List<Offer> offerList = new ArrayList<>();
        List<Benchmark> benchmarkList = new ArrayList<>();
        for (int index = 0; index < SYNTHETIC_PER_CATEGORY; index++) {
            addCpu(index, hardware, offerList, benchmarkList);
            addMotherboard(index, hardware, offerList);
            addMemory(index, hardware, offerList);
            addGpu(index, hardware, offerList, benchmarkList);
            addPsu(index, hardware, offerList);
            addCase(index, hardware, offerList);
            addCooler(index, hardware, offerList);
            addStorage(index, hardware, offerList);
        }
        return new SyntheticDataset(List.copyOf(hardware), List.copyOf(offerList),
                List.copyOf(benchmarkList));
    }

    private void addCpu(int index, List<Hardware> hardware, List<Offer> offers,
            List<Benchmark> benchmarks) {
        Hardware cpu = syntheticHardware("bench-cpu-" + index, HardwareCategory.CPU,
                "{\"socket\":\"AM5\",\"core_count\":" + (6 + index % 10)
                        + ",\"thread_count\":" + (12 + index % 20)
                        + ",\"tdp_w\":" + (125 + index % 55) + "}");
        hardware.add(cpu);
        offers.add(syntheticOffer(cpu, 250_000L + index * 1_000L));
        benchmarks.add(new Benchmark(cpu.hardwareId(), "CPUMARK", 20_000.0 + index * 50.0,
                3_000.0 + index * 10.0, 1, 100, "BENCH", 1.0, "bench"));
    }

    private void addMotherboard(int index, List<Hardware> hardware, List<Offer> offers) {
        Hardware motherboard = syntheticHardware("bench-mb-" + index, HardwareCategory.MOTHERBOARD,
                "{\"socket\":\"AM5\",\"form_factor\":\"ATX\",\"memory_type\":\"DDR5\","
                        + "\"memory_slots\":4,\"m2_slot_count\":2,\"sata_ports\":0}");
        hardware.add(motherboard);
        offers.add(syntheticOffer(motherboard, 220_000L + index * 1_000L));
    }

    private void addMemory(int index, List<Hardware> hardware, List<Offer> offers) {
        Hardware memory = syntheticHardware("bench-mem-" + index, HardwareCategory.MEMORY,
                "{\"memory_type\":\"DDR5\",\"capacity_gb\":32,\"module_count\":2,"
                        + "\"module_size_gb\":16,\"speed_mts\":6000,\"cas_latency\":30}");
        hardware.add(memory);
        offers.add(syntheticOffer(memory, 130_000L + index * 800L));
    }

    private void addGpu(int index, List<Hardware> hardware, List<Offer> offers,
            List<Benchmark> benchmarks) {
        Hardware gpu = syntheticHardware("bench-gpu-" + index, HardwareCategory.GPU,
                "{\"chipset\":\"bench\",\"vram_gb\":" + (8 + index % 12)
                        + ",\"length_mm\":" + (200 + index % 12 * 10)
                        + ",\"tdp_w\":" + (300 + index % 12 * 10)
                        + ",\"external_power\":{\"connector_type\":\"PCIE_8PIN\",\"count\":1}}");
        hardware.add(gpu);
        offers.add(syntheticOffer(gpu, 450_000L + index * 2_000L));
        benchmarks.add(new Benchmark(gpu.hardwareId(), "G3D_MARK", 10_000.0 + index * 100.0,
                1_200.0, 1, 100, "BENCH", 1.0, "bench"));
    }

    private void addPsu(int index, List<Hardware> hardware, List<Offer> offers) {
        // 仅 index % 8 == 0 的候选功率足够，其余在 GPU_PSU_POWER 增量规则处被剪枝。
        int wattage = index % 8 == 0 ? 850 : 400;
        Hardware psu = syntheticHardware("bench-psu-" + index, HardwareCategory.PSU,
                "{\"wattage_w\":" + wattage + ",\"pcie_8pin_count\":4,\"pcie_12vhpwr_count\":1}");
        hardware.add(psu);
        offers.add(syntheticOffer(psu, 110_000L + index * 1_000L));
    }

    private void addCase(int index, List<Hardware> hardware, List<Offer> offers) {
        // 一半机箱显卡限长不足，在 GPU_CASE_LENGTH 增量规则处被剪枝。
        int maxGpuLength = index % 8 == 0 || index % 8 == 4 ? 350 : 150;
        Hardware pcCase = syntheticHardware("bench-case-" + index, HardwareCategory.CASE,
                "{\"supported_mainboard_form_factors\":[\"ATX\"],"
                        + "\"max_gpu_length_mm\":" + maxGpuLength + ",\"max_cooler_height_mm\":170}");
        hardware.add(pcCase);
        offers.add(syntheticOffer(pcCase, 70_000L + index * 1_000L));
    }

    private void addCooler(int index, List<Hardware> hardware, List<Offer> offers) {
        // 仅 1/8 散热器支持 AM5，其余在 COOLER_CPU_SOCKET 增量规则处被剪枝。
        String socket = index % 8 == 0 ? "AM5" : "LGA1700";
        Hardware cooler = syntheticHardware("bench-cooler-" + index, HardwareCategory.COOLER,
                "{\"supported_sockets\":[\"" + socket + "\"],\"height_mm\":150,"
                        + "\"cooler_type\":\"AIR\"}");
        hardware.add(cooler);
        offers.add(syntheticOffer(cooler, 55_000L + index * 800L));
    }

    private void addStorage(int index, List<Hardware> hardware, List<Offer> offers) {
        // 主板没有 SATA 口，SATA 存储在 STORAGE_MOTHERBOARD_M2 处失败。
        String interfaceType = index % 8 == 0 ? "M.2" : "SATA";
        Hardware storage = syntheticHardware("bench-storage-" + index, HardwareCategory.STORAGE,
                "{\"interface\":\"" + interfaceType + "\","
                        + "\"form_factor\":\"" + ("M.2".equals(interfaceType) ? "M.2 2280" : "2.5 inch")
                        + "\",\"capacity_gb\":1024}");
        hardware.add(storage);
        offers.add(syntheticOffer(storage, 90_000L + index * 1_000L));
    }

    private Hardware syntheticHardware(String hardwareId, HardwareCategory category, String specJson) {
        HardwareSpecifications specifications = OBJECT_MAPPER.readValue(specJson, HardwareSpecifications.class);
        return new Hardware(hardwareId, category, "bench", "bench", null, null, specifications,
                "VERIFIED", "CURRENT", "ELIGIBLE");
    }

    private Offer syntheticOffer(Hardware hardware, long priceFen) {
        return new Offer("offer-" + hardware.hardwareId(), hardware.hardwareId(), hardware.category(),
                "BENCH", "bench", "bench", "bench", "sku", priceFen, "NORMAL",
                "https://example.invalid", null, null, Offer.MATCH_MOCK, "MOCK_DEMO", null);
    }

    private record SyntheticDataset(
            List<Hardware> hardware,
            List<Offer> offers,
            List<Benchmark> benchmarks) {
    }

    /** 统计兼容性规则调用次数；超类 {@code validate} 内部调用 {@code check} 也会被计入。 */
    private static final class CountingValidator extends CompatibilityValidator {

        private long checkCalls;

        private long validateCalls;

        private long successfulValidateCalls;

        @Override
        public CompatibilityCheck check(CompatibilityRule rule, HardwareSelection selection) {
            checkCalls++;
            return super.check(rule, selection);
        }

        @Override
        public CompatibilityReport validate(HardwareSelection selection) {
            validateCalls++;
            CompatibilityReport report = super.validate(selection);
            if (!report.hasFailure()) {
                successfulValidateCalls++;
            }
            return report;
        }
    }
}
