package com.example.agent.pcbuild.application;

import com.example.agent.pcbuild.domain.Benchmark;
import com.example.agent.pcbuild.domain.BuildDraft;
import com.example.agent.pcbuild.domain.BuildRequirements;
import com.example.agent.pcbuild.domain.BuildScoring;
import com.example.agent.pcbuild.domain.CompatibilityReport;
import com.example.agent.pcbuild.domain.CompatibilityRule;
import com.example.agent.pcbuild.domain.CompatibilityStatus;
import com.example.agent.pcbuild.domain.Hardware;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.HardwareSelection;
import com.example.agent.pcbuild.domain.Offer;
import com.example.agent.pcbuild.domain.SolveFailure;
import com.example.agent.pcbuild.domain.SolveFailureReason;
import com.example.agent.pcbuild.domain.SolveOutcome;
import com.example.agent.pcbuild.domain.WorkloadProfile;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/**
 * 确定性配置求解器。
 *
 * <p>流程：候选过滤 → 兼容性增量剪枝 → 预算剪枝 → 确定性搜索 → 场景评分。
 * 所有排序键都显式声明，禁止依赖 {@code HashMap} 迭代顺序；金额全程 {@code long} 分，
 * 不使用浮点。无解时返回结构化原因，绝不放宽预算或忽略硬冲突。</p>
 */
@Component
@RequiredArgsConstructor
public class BuildSolver {

    /** CPU/GPU 候选上限，控制搜索空间。 */
    private static final int PERFORMANCE_CANDIDATE_LIMIT = 12;

    /** 其他类别候选上限。 */
    private static final int COMPONENT_CANDIDATE_LIMIT = 8;

    /**
     * 有预算时，CPU/GPU 候选池中保留的最低价格档位数。
     *
     * <p>只按跑分截断会让「性能最高的 12 个」清一色高端型号；真实价格下这些型号任意组合
     * 都超过中端预算，入门/中端型号进不了池，可行预算反被判成 {@code BUDGET_EXCEEDED}。
     * 因此预算场景必须同时保留价格最低的一批候选，给搜索提供「降级到可负担」的出口。</p>
     */
    private static final int BUDGET_PRICE_TIER_QUOTA = 4;

    /** 性价比换算系数，用于避免浮点除法。 */
    private static final long VALUE_SCALE = 1_000_000L;

    /**
     * 搜索顺序：约束最强的类别先枚举，尽早触发兼容性与预算剪枝。
     */
    private static final List<HardwareCategory> SEARCH_ORDER = List.of(
            HardwareCategory.CPU,
            HardwareCategory.MOTHERBOARD,
            HardwareCategory.MEMORY,
            HardwareCategory.GPU,
            HardwareCategory.PSU,
            HardwareCategory.CASE,
            HardwareCategory.COOLER,
            HardwareCategory.STORAGE);

    /**
     * 每加入一个类别后立刻检查的规则；完整组合仍会再跑一次全量校验，避免遗漏。
     */
    private static final Map<HardwareCategory, List<CompatibilityRule>> INCREMENTAL_RULES = Map.of(
            HardwareCategory.MOTHERBOARD, List.of(CompatibilityRule.CPU_SOCKET_MOTHERBOARD),
            HardwareCategory.MEMORY, List.of(
                    CompatibilityRule.MOTHERBOARD_MEMORY_TYPE,
                    CompatibilityRule.MEMORY_MODULE_COUNT),
            HardwareCategory.PSU, List.of(CompatibilityRule.GPU_PSU_POWER),
            HardwareCategory.CASE, List.of(
                    CompatibilityRule.MOTHERBOARD_CASE_FORM_FACTOR,
                    CompatibilityRule.GPU_CASE_LENGTH),
            HardwareCategory.COOLER, List.of(
                    CompatibilityRule.COOLER_CPU_SOCKET,
                    CompatibilityRule.COOLER_CASE_HEIGHT),
            HardwareCategory.STORAGE, List.of(CompatibilityRule.STORAGE_MOTHERBOARD_M2));

    private final CompatibilityValidator compatibilityValidator;

    /**
     * 求解一套配置。
     *
     * @param requirements   需求
     * @param catalog        候选硬件全集
     * @param offers         报价全集
     * @param benchmarks     跑分全集
     * @param catalogVersion 目录版本
     * @param offerDataStatus 报价数据状态
     * @param pricingDate    询价日期，用于判断报价有效期
     * @return 成功方案或结构化失败
     */
    public SolveOutcome solve(
            BuildRequirements requirements,
            List<Hardware> catalog,
            List<Offer> offers,
            List<Benchmark> benchmarks,
            String catalogVersion,
            String offerDataStatus,
            LocalDate pricingDate) {

        Map<String, Offer> cheapestOffers = cheapestUsableOffers(
                offers, pricingDate, requirements.requireVerifiedOffers());
        Map<String, Benchmark> benchmarkIndex = new HashMap<>();
        for (Benchmark benchmark : benchmarks) {
            benchmarkIndex.put(benchmark.hardwareId(), benchmark);
        }

        Map<HardwareCategory, List<Candidate>> rawPools = collectRawPools(
                catalog, cheapestOffers, benchmarkIndex, requirements);
        Map<HardwareCategory, List<Candidate>> pools = buildCompatiblePools(
                rawPools, requirements, requirements.hasBudget());
        Map<String, Integer> candidateCounts = new LinkedHashMap<>();
        List<String> missingCategories = new ArrayList<>();
        for (HardwareCategory category : HardwareCategory.REQUIRED_CATEGORIES) {
            List<Candidate> pool = pools.getOrDefault(category, List.of());
            candidateCounts.put(category.name(), pool.size());
            if (pool.isEmpty()) {
                missingCategories.add(category.name());
            }
        }
        if (!missingCategories.isEmpty()) {
            return SolveOutcome.failed(new SolveFailure(
                    SolveFailureReason.NO_CANDIDATES,
                    "以下类别没有可参与求解的候选：" + String.join("、", missingCategories)
                            + "（缺少有效报价、跑分或未满足容量筛选）",
                    missingCategories,
                    candidateCounts,
                    null,
                    0));
        }

        SearchContext context = new SearchContext(requirements, pools, benchmarkIndex);
        search(0, HardwareSelection.empty(), 0L, context, requirements.budgetMaxFen(), true);
        long minimumRequiredBudgetFen = context.minCompatiblePrice;
        int evaluatedCombinations = context.evaluatedCombinations;
        if (context.bestSelection == null && requirements.hasBudget()) {
            // 预算剪枝会跳过超预算分支；用独立探针再跑一轮无预算搜索，
            // 只取「最低可行总价」，绝不能把探针命中的超预算方案当作结果返回。
            // 探针必须基于「未按预算裁剪」的候选池，否则候选上限会挤掉超预算但更高分的型号，
            // 导致最低可行总价被低估（后续按该金额求解反而得到更贵的方案）。
            Map<HardwareCategory, List<Candidate>> unboundedPools = buildCompatiblePools(
                    collectRawPools(catalog, cheapestOffers, benchmarkIndex, requirements.withoutBudget()),
                    requirements,
                    true);
            SearchContext probe = new SearchContext(requirements, unboundedPools, benchmarkIndex);
            search(0, HardwareSelection.empty(), 0L, probe, null, false);
            minimumRequiredBudgetFen = probe.minCompatiblePrice;
            evaluatedCombinations += probe.evaluatedCombinations;
        }

        if (context.bestSelection != null) {
            return SolveOutcome.solved(toDraft(context.bestSelection, context, catalogVersion, offerDataStatus));
        }
        if (requirements.hasBudget() && minimumRequiredBudgetFen != Long.MAX_VALUE) {
            return SolveOutcome.failed(new SolveFailure(
                    SolveFailureReason.BUDGET_EXCEEDED,
                    "预算 " + requirements.budgetMaxFen() + " 分不足以覆盖最低可行配置；最低可行总价为 "
                            + minimumRequiredBudgetFen + " 分，不会放宽预算",
                    List.of(),
                    candidateCounts,
                    minimumRequiredBudgetFen,
                    evaluatedCombinations));
        }
        return SolveOutcome.failed(new SolveFailure(
                SolveFailureReason.NO_COMPATIBLE_BUILD,
                "候选存在，但没有任何组合通过八条兼容性规则",
                List.of(),
                candidateCounts,
                null,
                evaluatedCombinations));
    }

    /**
     * 为全部必需类别收集未截断的候选；预算存在时，单件超预算的候选会被剔除。
     */
    private Map<HardwareCategory, List<Candidate>> collectRawPools(
            List<Hardware> catalog,
            Map<String, Offer> cheapestOffers,
            Map<String, Benchmark> benchmarkIndex,
            BuildRequirements requirements) {

        Map<HardwareCategory, List<Candidate>> rawPools = new LinkedHashMap<>();
        for (HardwareCategory category : HardwareCategory.REQUIRED_CATEGORIES) {
            rawPools.put(category,
                    candidatesOf(category, catalog, cheapestOffers, benchmarkIndex, requirements));
        }
        return rawPools;
    }

    private List<Candidate> candidatesOf(
            HardwareCategory category,
            List<Hardware> catalog,
            Map<String, Offer> cheapestOffers,
            Map<String, Benchmark> benchmarkIndex,
            BuildRequirements requirements) {

        List<Candidate> candidates = new ArrayList<>();
        for (Hardware hardware : catalog) {
            if (hardware.category() != category || !hardware.isSolverEligible()) {
                continue;
            }
            if (!meetsCapacityRequirement(hardware, requirements)) {
                continue;
            }
            Offer offer = cheapestOffers.get(hardware.hardwareId());
            if (offer == null) {
                continue;
            }
            Benchmark benchmark = benchmarkIndex.get(hardware.hardwareId());
            long performanceScore = benchmark == null ? 0L : Math.max(0L, benchmark.scoreAsLong());
            long secondaryScore = benchmark == null || benchmark.secondaryScore() == null
                    ? 0L
                    : Math.max(0L, Math.round(benchmark.secondaryScore()));
            candidates.add(new Candidate(hardware, offer, benchmark, performanceScore, secondaryScore));
        }
        Long budgetMaxFen = requirements.budgetMaxFen();
        if (budgetMaxFen != null) {
            // 单件就超预算的组合永远不可行；不提前剔除，高价件会占满候选上限，
            // 把可负担的型号挤出候选池（AI 场景按显存排序时尤其明显）。
            List<Candidate> affordable = candidates.stream()
                    .filter(candidate -> candidate.offer().priceFen() <= budgetMaxFen)
                    .toList();
            // 全部超预算时保留原候选，让上层给出 BUDGET_EXCEEDED 而不是 NO_CANDIDATES。
            if (!affordable.isEmpty()) {
                return affordable;
            }
        }
        return candidates;
    }

    /**
     * 构建兼容感知的候选池：先按插槽与内存类型过滤，再按画像排序截断。
     *
     * <p><b>为什么必须先过滤再截断：</b>运行时目录已从数十条扩到数百条（主板 65、内存 16、
     * 散热 66 等），若仍按价格取前 N，内存会取到清一色 DDR4，而主板全是 DDR5，
     * {@code MOTHERBOARD_MEMORY_TYPE} 对任意组合都返回 {@code FAIL}，DFS 搜索再完整也只会得到无解。
     * 这是数据规模扩大后暴露的真实缺陷，不是排序偏好；同理主板要先收敛到已截断 CPU 池的插槽，
     * 散热器要先收敛到这些插槽，机箱要先收敛到主板板型与显卡限长，否则同样会整池失配。</p>
     *
     * <p>过滤只剔除「校验器确定会判 FAIL」的候选：字段缺失时校验器返回 {@code UNKNOWN}，
     * 因此缺失 socket / memory_type / supported_sockets 的候选必须保留，避免把可能可行的组合提前排除。</p>
     *
     * @param rawPools     按类别收集、尚未排序截断的候选
     * @param requirements 求解需求，排序策略取自 {@link BuildRequirements#workloadProfile()}
     * @param keepPriceTiers 是否在 CPU/GPU 池中额外保留最低价候选，预算场景必须为 {@code true}
     * @return 覆盖全部 {@link HardwareCategory#REQUIRED_CATEGORIES} 的兼容候选池
     */
    private Map<HardwareCategory, List<Candidate>> buildCompatiblePools(
            Map<HardwareCategory, List<Candidate>> rawPools,
            BuildRequirements requirements,
            boolean keepPriceTiers) {

        WorkloadProfile profile = requirements.workloadProfile();
        Map<HardwareCategory, List<Candidate>> pools = new LinkedHashMap<>();

        List<Candidate> cpuPool = sortedTruncated(HardwareCategory.CPU,
                rawPools.getOrDefault(HardwareCategory.CPU, List.of()), profile, keepPriceTiers);
        pools.put(HardwareCategory.CPU, cpuPool);

        List<Candidate> motherboardPool = sortedTruncated(HardwareCategory.MOTHERBOARD,
                filterBySocket(rawPools.getOrDefault(HardwareCategory.MOTHERBOARD, List.of()),
                        socketKeysOf(cpuPool)),
                profile, keepPriceTiers);
        pools.put(HardwareCategory.MOTHERBOARD, motherboardPool);
        pools.put(HardwareCategory.MEMORY, sortedTruncated(HardwareCategory.MEMORY,
                filterByMemoryType(rawPools.getOrDefault(HardwareCategory.MEMORY, List.of()),
                        motherboardPool),
                profile, keepPriceTiers));
        List<Candidate> gpuPool = sortedTruncated(HardwareCategory.GPU,
                rawPools.getOrDefault(HardwareCategory.GPU, List.of()), profile, keepPriceTiers);
        pools.put(HardwareCategory.GPU, gpuPool);
        pools.put(HardwareCategory.PSU, sortedTruncated(HardwareCategory.PSU,
                rawPools.getOrDefault(HardwareCategory.PSU, List.of()), profile, keepPriceTiers));
        // 机箱同样要先收敛到主板池板型与显卡池限长：最低价的 8 个机箱可能清一色 Mini ITX，
        // 而主板池是 Micro ATX，截断后 MOTHERBOARD_CASE_FORM_FACTOR 对任意组合都 FAIL。
        pools.put(HardwareCategory.CASE, sortedTruncated(HardwareCategory.CASE,
                filterByGpuLength(
                        filterByMotherboardFormFactor(
                                rawPools.getOrDefault(HardwareCategory.CASE, List.of()),
                                motherboardPool),
                        gpuPool),
                profile, keepPriceTiers));
        pools.put(HardwareCategory.COOLER, sortedTruncated(HardwareCategory.COOLER,
                filterBySupportedSockets(rawPools.getOrDefault(HardwareCategory.COOLER, List.of()),
                        cpuPool),
                profile, keepPriceTiers));
        pools.put(HardwareCategory.STORAGE, sortedTruncated(HardwareCategory.STORAGE,
                rawPools.getOrDefault(HardwareCategory.STORAGE, List.of()), profile, keepPriceTiers));
        return pools;
    }

    /**
     * 按画像策略排序后截断到类别上限，控制搜索空间。
     *
     * <p>有预算时 CPU/GPU 额外保留价格最低的一批候选：若只取性能前 N，真实价格下的
     * 入门/中端型号永远进不了池，中端预算会被误判为不可行。</p>
     */
    private List<Candidate> sortedTruncated(
            HardwareCategory category,
            List<Candidate> candidates,
            WorkloadProfile profile,
            boolean keepPriceTiers) {

        List<Candidate> sorted = new ArrayList<>(candidates);
        sorted.sort(candidateOrder(category, profile));
        int limit = category == HardwareCategory.CPU || category == HardwareCategory.GPU
                ? PERFORMANCE_CANDIDATE_LIMIT
                : COMPONENT_CANDIDATE_LIMIT;
        if (!keepPriceTiers
                || (category != HardwareCategory.CPU && category != HardwareCategory.GPU)
                || sorted.size() <= limit) {
            return List.copyOf(sorted.subList(0, Math.min(limit, sorted.size())));
        }
        return selectPerformanceAndCheapest(candidates, sorted, limit);
    }

    /**
     * 选取「性能前 N」与「价格最低 M」的并集，两类合计不超过 {@code limit}。
     *
     * <p>数量不变（仍为 {@code limit}），因此不会放大搜索空间；只是把被高价段挤掉的
     * 可负担候选补回池中。结果按性能序排列，价格档位按价格升序追加。</p>
     */
    private List<Candidate> selectPerformanceAndCheapest(
            List<Candidate> candidates, List<Candidate> sortedByPerformance, int limit) {

        int cheapQuota = Math.min(BUDGET_PRICE_TIER_QUOTA, limit / 2);
        int performanceQuota = limit - cheapQuota;
        Set<String> selectedIds = new HashSet<>();
        List<Candidate> selected = new ArrayList<>(limit);
        for (Candidate candidate : sortedByPerformance) {
            if (selected.size() >= performanceQuota) {
                break;
            }
            selected.add(candidate);
            selectedIds.add(candidate.hardware().hardwareId());
        }
        List<Candidate> byPrice = new ArrayList<>(candidates);
        byPrice.sort(Comparator.comparingLong((Candidate candidate) -> candidate.offer().priceFen())
                .thenComparing(candidate -> candidate.hardware().hardwareId()));
        for (Candidate candidate : byPrice) {
            if (selected.size() >= limit) {
                break;
            }
            if (selectedIds.add(candidate.hardware().hardwareId())) {
                selected.add(candidate);
            }
        }
        return List.copyOf(selected);
    }

    /**
     * 保留 socket 命中 CPU 池的候选。
     *
     * <p>与校验器一致：socket 为空的候选保留（校验器判 {@code UNKNOWN}）；
     * CPU 池中只要有一颗 CPU 缺少 socket，也无法断定任何主板会 {@code FAIL}，同样全部保留。</p>
     */
    private List<Candidate> filterBySocket(List<Candidate> candidates, CompatibilityKeys cpuSockets) {
        List<Candidate> compatible = new ArrayList<>();
        for (Candidate candidate : candidates) {
            String socket = candidate.hardware().specifications().socket();
            if (isBlank(socket) || cpuSockets.matches(socket)) {
                compatible.add(candidate);
            }
        }
        return compatible;
    }

    /**
     * 保留内存类型命中主板池的候选；内存类型缺失时保留，理由同 {@link #filterBySocket}。
     */
    private List<Candidate> filterByMemoryType(List<Candidate> memories, List<Candidate> motherboardPool) {
        CompatibilityKeys boardTypes = memoryTypesOf(motherboardPool);
        List<Candidate> compatible = new ArrayList<>();
        for (Candidate memory : memories) {
            String memoryType = memory.hardware().specifications().memoryType();
            if (isBlank(memoryType) || boardTypes.matches(memoryType)) {
                compatible.add(memory);
            }
        }
        return compatible;
    }

    /**
     * 保留支持 CPU 池任一插槽的散热器。
     *
     * <p>与 {@code COOLER_CPU_SOCKET} 校验器一致：支持列表缺失或为空时校验器判 {@code UNKNOWN}，
     * 必须保留；CPU 池中存在缺失 socket 的 CPU 时也不能提前排除任何散热器。</p>
     */
    private List<Candidate> filterBySupportedSockets(List<Candidate> coolers, List<Candidate> cpuPool) {
        CompatibilityKeys cpuSockets = socketKeysOf(cpuPool);
        List<Candidate> compatible = new ArrayList<>();
        for (Candidate cooler : coolers) {
            List<String> supportedSockets = cooler.hardware().specifications().supportedSockets();
            if (supportedSockets == null || supportedSockets.isEmpty()) {
                compatible.add(cooler);
                continue;
            }
            boolean isSupported = supportedSockets.stream()
                    .filter(Objects::nonNull)
                    .anyMatch(cpuSockets::matches);
            if (isSupported) {
                compatible.add(cooler);
            }
        }
        return compatible;
    }

    /**
     * 保留支持主板池任一板型的机箱。
     *
     * <p>与 {@code MOTHERBOARD_CASE_FORM_FACTOR} 校验器一致：机箱支持列表缺失或为空时校验器判
     * {@code UNKNOWN}，必须保留；主板池中存在缺失板型的主板时同样无法断定任何机箱会
     * {@code FAIL}，也全部保留。</p>
     */
    private List<Candidate> filterByMotherboardFormFactor(
            List<Candidate> cases, List<Candidate> motherboardPool) {

        CompatibilityKeys boardFormFactors = formFactorsOf(motherboardPool);
        List<Candidate> compatible = new ArrayList<>();
        for (Candidate pcCase : cases) {
            List<String> supported = pcCase.hardware().specifications()
                    .supportedMainboardFormFactors();
            if (supported == null || supported.isEmpty()) {
                compatible.add(pcCase);
                continue;
            }
            boolean isSupported = supported.stream()
                    .filter(Objects::nonNull)
                    .anyMatch(boardFormFactors::matches);
            if (isSupported) {
                compatible.add(pcCase);
            }
        }
        return compatible;
    }

    /**
     * 保留至少能装下显卡池中一张显卡的机箱。
     *
     * <p>与 {@code GPU_CASE_LENGTH} 校验器一致：机箱限长或显卡长度缺失时判 {@code UNKNOWN}，
     * 不能据此排除候选。取显卡池最短长度做必要条件判断，只剔除确定装不下的机箱。</p>
     */
    private List<Candidate> filterByGpuLength(List<Candidate> cases, List<Candidate> gpuPool) {
        int shortestGpuLength = Integer.MAX_VALUE;
        boolean hasMissingLength = false;
        for (Candidate gpu : gpuPool) {
            Integer length = gpu.hardware().specifications().lengthMm();
            if (length == null) {
                hasMissingLength = true;
            } else {
                shortestGpuLength = Math.min(shortestGpuLength, length);
            }
        }
        List<Candidate> compatible = new ArrayList<>();
        for (Candidate pcCase : cases) {
            Integer maxLength = pcCase.hardware().specifications().maxGpuLengthMm();
            if (maxLength == null || hasMissingLength || gpuPool.isEmpty()
                    || shortestGpuLength <= maxLength) {
                compatible.add(pcCase);
            }
        }
        return compatible;
    }

    /**
     * 收集一组主板的非空板型；存在缺失板型时标记为「无法判定」，避免误删可行机箱。
     */
    private CompatibilityKeys formFactorsOf(List<Candidate> motherboards) {
        Set<String> formFactors = new HashSet<>();
        boolean hasMissingKey = false;
        for (Candidate motherboard : motherboards) {
            String formFactor = motherboard.hardware().specifications().formFactor();
            if (isBlank(formFactor)) {
                hasMissingKey = true;
            } else {
                formFactors.add(normalizeKey(formFactor));
            }
        }
        return new CompatibilityKeys(formFactors, hasMissingKey);
    }

    /**
     * 收集一组候选的非空 socket；存在缺失 socket 时标记为「无法判定」，由校验器最终判 {@code UNKNOWN}。
     */
    private CompatibilityKeys socketKeysOf(List<Candidate> candidates) {
        Set<String> sockets = new HashSet<>();
        boolean hasMissingKey = false;
        for (Candidate candidate : candidates) {
            String socket = candidate.hardware().specifications().socket();
            if (isBlank(socket)) {
                hasMissingKey = true;
            } else {
                sockets.add(normalizeKey(socket));
            }
        }
        return new CompatibilityKeys(sockets, hasMissingKey);
    }

    /**
     * 收集一组主板的非空内存类型；存在缺失类型时标记为「无法判定」，避免误删可行内存。
     */
    private CompatibilityKeys memoryTypesOf(List<Candidate> motherboards) {
        Set<String> memoryTypes = new HashSet<>();
        boolean hasMissingKey = false;
        for (Candidate motherboard : motherboards) {
            String memoryType = motherboard.hardware().specifications().memoryType();
            if (isBlank(memoryType)) {
                hasMissingKey = true;
            } else {
                memoryTypes.add(normalizeKey(memoryType));
            }
        }
        return new CompatibilityKeys(memoryTypes, hasMissingKey);
    }

    /**
     * 与校验器一致的忽略大小写比较；额外 trim 只会让更多候选通过，不会误删可行候选。
     */
    private static String normalizeKey(String value) {
        return value.trim().toLowerCase(Locale.ROOT);
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    /**
     * 过滤依赖的取键结果；{@code hasMissingKey} 表示参考池中存在无法判定的字段，
     * 此时不能据此排除任何候选（校验器会返回 {@code UNKNOWN} 而不是 {@code FAIL}）。
     */
    private record CompatibilityKeys(Set<String> keys, boolean hasMissingKey) {

        boolean matches(String value) {
            return hasMissingKey || keys.contains(normalizeKey(value));
        }
    }

    /**
     * 按画像的候选排序策略生成比较器；所有分支都以 {@code hardwareId} 升序兜底，
     * 保证同一输入在任意 JVM 上都得到相同候选顺序。
     */
    private Comparator<Candidate> candidateOrder(
            HardwareCategory category, WorkloadProfile workloadProfile) {
        return switch (workloadProfile.candidateRanking()) {
            case BALANCED -> defaultOrder(category);
            case SINGLE_THREAD_FIRST -> category == HardwareCategory.CPU
                    ? singleThreadFirstOrder()
                    : defaultOrder(category);
            case MULTICORE_FIRST -> category == HardwareCategory.CPU
                    ? multicoreFirstOrder()
                    : defaultOrder(category);
            case VRAM_FIRST -> category == HardwareCategory.GPU
                    ? vramFirstOrder()
                    : defaultOrder(category);
            case GPU_SCORE_FIRST -> category == HardwareCategory.STORAGE
                    ? capacityFirstOrder()
                    : defaultOrder(category);
        };
    }

    private Comparator<Candidate> defaultOrder(HardwareCategory category) {
        if (category == HardwareCategory.CPU || category == HardwareCategory.GPU) {
            return performanceFirstOrder();
        }
        return priceFirstOrder();
    }

    private Comparator<Candidate> performanceFirstOrder() {
        return Comparator.comparingLong(Candidate::performanceScore).reversed()
                .thenComparingLong(candidate -> candidate.offer().priceFen())
                .thenComparing(candidate -> candidate.hardware().hardwareId());
    }

    private Comparator<Candidate> priceFirstOrder() {
        return Comparator.comparingLong((Candidate candidate) -> candidate.offer().priceFen())
                .thenComparing(candidate -> candidate.hardware().hardwareId());
    }

    private Comparator<Candidate> singleThreadFirstOrder() {
        return Comparator.comparingLong(Candidate::secondaryScore).reversed()
                .thenComparing(Comparator.comparingLong(Candidate::performanceScore).reversed())
                .thenComparingLong(candidate -> candidate.offer().priceFen())
                .thenComparing(candidate -> candidate.hardware().hardwareId());
    }

    private Comparator<Candidate> multicoreFirstOrder() {
        return Comparator.comparingLong(Candidate::coreCount).reversed()
                .thenComparing(Comparator.comparingLong(Candidate::performanceScore).reversed())
                .thenComparingLong(candidate -> candidate.offer().priceFen())
                .thenComparing(candidate -> candidate.hardware().hardwareId());
    }

    private Comparator<Candidate> vramFirstOrder() {
        return Comparator.comparingLong(Candidate::vramGb).reversed()
                .thenComparing(Comparator.comparingLong(Candidate::performanceScore).reversed())
                .thenComparingLong(candidate -> candidate.offer().priceFen())
                .thenComparing(candidate -> candidate.hardware().hardwareId());
    }

    private Comparator<Candidate> capacityFirstOrder() {
        return Comparator.comparingLong(Candidate::capacityGb).reversed()
                .thenComparingLong(candidate -> candidate.offer().priceFen())
                .thenComparing(candidate -> candidate.hardware().hardwareId());
    }

    private boolean meetsCapacityRequirement(Hardware hardware, BuildRequirements requirements) {
        if (hardware.category() == HardwareCategory.MEMORY && requirements.minMemoryGb() != null) {
            Integer capacity = hardware.specifications().capacityGb();
            return capacity != null && capacity >= requirements.minMemoryGb();
        }
        if (hardware.category() == HardwareCategory.STORAGE && requirements.minStorageGb() != null) {
            Integer capacity = hardware.specifications().capacityGb();
            return capacity != null && capacity >= requirements.minStorageGb();
        }
        return true;
    }

    private Map<String, Offer> cheapestUsableOffers(
            List<Offer> offers, LocalDate pricingDate, boolean requireVerified) {
        Map<String, Offer> cheapest = new HashMap<>();
        for (Offer offer : offers) {
            if (!offer.isUsableOn(pricingDate)) {
                continue;
            }
            if (requireVerified && !offer.isVerifiedPrice()) {
                continue;
            }
            cheapest.merge(offer.hardwareId(), offer, (left, right) -> {
                if (left.priceFen() != right.priceFen()) {
                    return left.priceFen() <= right.priceFen() ? left : right;
                }
                return left.offerId().compareTo(right.offerId()) <= 0 ? left : right;
            });
        }
        return Map.copyOf(cheapest);
    }

    /**
     * 深度优先搜索，按 {@link #SEARCH_ORDER} 固定顺序枚举。
     *
     * @param depth      当前类别下标
     * @param selection  已选组合
     * @param price      已选总价
     * @param context    搜索上下文
     * @param budgetLimit 预算上限；{@code null} 表示不剪枝
     * @param trackBest  是否更新最优方案；探针搜索只统计最低可行价
     */
    private void search(
            int depth,
            HardwareSelection selection,
            long price,
            SearchContext context,
            Long budgetLimit,
            boolean trackBest) {

        if (depth == SEARCH_ORDER.size()) {
            evaluateComplete(selection, price, context, budgetLimit, trackBest);
            return;
        }
        HardwareCategory category = SEARCH_ORDER.get(depth);
        for (Candidate candidate : context.pools.get(category)) {
            HardwareSelection next = selection.with(category, candidate.hardware());
            if (violatesIncrementalRules(category, next)) {
                continue;
            }
            long nextPrice = price + candidate.offer().priceFen();
            // 报价为正，后续只增不减，因此超出预算可以安全剪枝。
            if (budgetLimit != null && nextPrice > budgetLimit) {
                continue;
            }
            search(depth + 1, next, nextPrice, context, budgetLimit, trackBest);
        }
    }

    private boolean violatesIncrementalRules(HardwareCategory category, HardwareSelection selection) {
        List<CompatibilityRule> rules = INCREMENTAL_RULES.get(category);
        if (rules == null) {
            return false;
        }
        for (CompatibilityRule rule : rules) {
            if (compatibilityValidator.check(rule, selection).status() == CompatibilityStatus.FAIL) {
                return true;
            }
        }
        return false;
    }

    private void evaluateComplete(
            HardwareSelection selection,
            long price,
            SearchContext context,
            Long budgetLimit,
            boolean trackBest) {

        CompatibilityReport report = compatibilityValidator.validate(selection);
        if (report.hasFailure()) {
            return;
        }
        context.evaluatedCombinations++;
        context.minCompatiblePrice = Math.min(context.minCompatiblePrice, price);
        if (!trackBest) {
            return;
        }
        if (budgetLimit != null && price > budgetLimit) {
            return;
        }
        long score = scoreOf(selection, context);
        String ids = selection.idSignature();
        if (isBetter(context, score, price, ids)) {
            context.bestSelection = selection;
            context.bestScore = score;
            context.bestPrice = price;
            context.bestIds = ids;
        }
    }

    private long scoreOf(HardwareSelection selection, SearchContext context) {
        return BuildScoring.totalScore(
                context.requirements, selection.asMap(), context.benchmarkIndex);
    }

    private boolean isBetter(SearchContext context, long score, long price, String ids) {
        if (context.bestSelection == null) {
            return true;
        }
        // 无预算时沿用历史性价比策略；有预算时只有显式 VALUE 才改用性价比排序。
        boolean isValueStrategy = !context.requirements.hasBudget()
                || context.requirements.prefersValue();
        if (isValueStrategy) {
            long value = valueOf(score, price);
            long bestValue = valueOf(context.bestScore, context.bestPrice);
            if (value != bestValue) {
                return value > bestValue;
            }
            if (score != context.bestScore) {
                return score > context.bestScore;
            }
        } else if (score != context.bestScore) {
            return score > context.bestScore;
        }
        if (price != context.bestPrice) {
            return price < context.bestPrice;
        }
        return ids.compareTo(context.bestIds) < 0;
    }

    private long valueOf(long score, long price) {
        return price <= 0L ? 0L : score * VALUE_SCALE / price;
    }

    private BuildDraft toDraft(
            HardwareSelection selection,
            SearchContext context,
            String catalogVersion,
            String offerDataStatus) {

        Map<HardwareCategory, Offer> offers = new LinkedHashMap<>();
        Map<HardwareCategory, Benchmark> benchmarks = new LinkedHashMap<>();
        long totalPrice = 0L;
        for (HardwareCategory category : HardwareCategory.REQUIRED_CATEGORIES) {
            Hardware hardware = selection.get(category);
            Offer offer = context.offerOf(hardware);
            totalPrice += offer.priceFen();
            offers.put(category, offer);
            Benchmark benchmark = context.benchmarkIndex.get(hardware.hardwareId());
            if (benchmark != null) {
                benchmarks.put(category, benchmark);
            }
        }
        CompatibilityReport report = compatibilityValidator.validate(selection);
        return new BuildDraft(
                context.requirements,
                selection,
                offers,
                benchmarks,
                totalPrice,
                report,
                scoreOf(selection, context),
                catalogVersion,
                offerDataStatus);
    }

    /** 单个候选：硬件 + 最低有效报价 + 跑分。 */
    private record Candidate(
            Hardware hardware,
            Offer offer,
            Benchmark benchmark,
            long performanceScore,
            long secondaryScore) {

        // 排序键直接从规格读取，不重复建模，避免出现两套可能失同步的字段。
        long coreCount() {
            return positiveOrZero(hardware.specifications().coreCount());
        }

        long vramGb() {
            return positiveOrZero(hardware.specifications().vramGb());
        }

        long capacityGb() {
            return positiveOrZero(hardware.specifications().capacityGb());
        }

        private static long positiveOrZero(Integer value) {
            return value == null ? 0L : Math.max(0, value);
        }
    }

    /** 搜索期间的可变上下文，避免在递归中传递大量参数。 */
    private static final class SearchContext {

        private final BuildRequirements requirements;
        private final Map<HardwareCategory, List<Candidate>> pools;
        private final Map<String, Benchmark> benchmarkIndex;
        private final Map<String, Offer> offersByHardware = new HashMap<>();

        private HardwareSelection bestSelection;
        private long bestScore = Long.MIN_VALUE;
        private long bestPrice;
        private String bestIds = "";
        private long minCompatiblePrice = Long.MAX_VALUE;
        private int evaluatedCombinations;

        private SearchContext(
                BuildRequirements requirements,
                Map<HardwareCategory, List<Candidate>> pools,
                Map<String, Benchmark> benchmarkIndex) {
            this.requirements = requirements;
            this.pools = pools;
            this.benchmarkIndex = benchmarkIndex;
            for (List<Candidate> pool : pools.values()) {
                for (Candidate candidate : pool) {
                    offersByHardware.put(candidate.hardware().hardwareId(), candidate.offer());
                }
            }
        }

        private Offer offerOf(Hardware hardware) {
            return Objects.requireNonNull(offersByHardware.get(hardware.hardwareId()),
                    () -> "缺少报价: " + hardware.hardwareId());
        }
    }

    /**
     * 便于测试与调用方判断某硬件是否有有效报价。
     *
     * @param offer 报价
     * @param asOf  询价日期
     * @return 有效时为 {@code true}
     */
    public static boolean isUsable(Offer offer, LocalDate asOf) {
        return Optional.ofNullable(offer).map(value -> value.isUsableOn(asOf)).orElse(false);
    }
}
