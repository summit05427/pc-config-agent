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
import java.util.function.Function;
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

    /**
     * CPU/GPU 价格分桶上界，单位分（1000 / 2000 / 4000 / 8000 元）；最后一档为开放式桶。
     *
     * <p>「性能前 N + 最低价 M」只在两端取样，中间价位段（1000–4000 元）整段缺失，
     * 求解器只能在高价旗舰与入门型号之间二选一，于是出现「低价 CPU + 旗舰 GPU」的畸形组合。
     * 按价格分桶补足后，每个价位段都有按画像排序的候选，搜索能在预算内找到均衡搭配。</p>
     */
    private static final long[] PRICE_BUCKET_UPPER_BOUNDS_FEN = {
        100_000L, 200_000L, 400_000L, 800_000L
    };

    /** 每个价格分桶按画像排序保留的候选数。 */
    private static final int PRICE_BUCKET_CANDIDATE_QUOTA = 2;

    /**
     * 内存按内存类型分组后每组的候选上限。
     *
     * <p>若按全库价格取前 N，低价 DDR4 会占满整池，DDR5 平台在搜索阶段必然失配；
     * 分组后每种类型都有配额，任何被保留的主板平台都能找到配套内存。</p>
     */
    private static final int MEMORY_TYPE_CANDIDATE_LIMIT = 8;

    /**
     * 主板按 (socket, memoryType) 平台分组后每组的候选上限。
     *
     * <p>主板同样是多代平台并存：只保留最便宜的若干条会让低价平台独占比率，
     * 高价平台的 CPU/内存组合进不了搜索。按平台分组保证每类平台都有可负担的主板。</p>
     */
    private static final int MOTHERBOARD_PLATFORM_CANDIDATE_LIMIT = 6;

    /** 分组键中缺失字段的占位符，保证所有「无法判定」的候选落在同一组。 */
    private static final String UNKNOWN_GROUP_KEY = "\u0000UNKNOWN";

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
            return SolveOutcome.solved(toDraft(
                    context.requirements,
                    context.bestSelection,
                    context.offersByHardware,
                    context.benchmarkIndex,
                    catalogVersion,
                    offerDataStatus));
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
     * <p>截断按类别分别处理：内存按内存类型、主板按 (socket, memoryType) 平台分组保留配额，
     * CPU/GPU 在「性能前 8 + 最低价 4」之外再按价格分桶补足中端型号。全库统一取前 N
     * 会让低价平台独占比率，其他平台在搜索阶段整池失配。</p>
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
                filterByQualityPrice(HardwareCategory.CPU,
                        rawPools.getOrDefault(HardwareCategory.CPU, List.of()), requirements),
                profile, keepPriceTiers);
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
                filterByQualityPrice(HardwareCategory.GPU,
                        rawPools.getOrDefault(HardwareCategory.GPU, List.of()), requirements),
                profile, keepPriceTiers);
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
     * 按质量约束裁剪 CPU/GPU 候选：CPU 保留价格不低于下限的型号，GPU 保留价格不高于上限的型号。
     *
     * <p>约束来自 Agent 质量评审的「带约束重解」，只为修正 CPU/GPU 价格失衡与办公场景显卡超支。
     * 约束把整类候选筛空时退回原候选，避免提示性约束把本可求解的问题变成
     * {@code NO_CANDIDATES}——质量问题是可降级的，可解性是不可降级的。</p>
     *
     * @param category     类别，仅 CPU/GPU 生效
     * @param candidates   原始候选
     * @param requirements 需求，提供价格约束
     * @return 裁剪后的候选；无约束或被筛空时返回原候选
     */
    private List<Candidate> filterByQualityPrice(
            HardwareCategory category, List<Candidate> candidates, BuildRequirements requirements) {

        Long bound = switch (category) {
            case CPU -> requirements.minCpuPriceFen();
            case GPU -> requirements.maxGpuPriceFen();
            default -> null;
        };
        if (bound == null) {
            return candidates;
        }
        boolean isLowerBound = category == HardwareCategory.CPU;
        List<Candidate> filtered = candidates.stream()
                .filter(candidate -> isLowerBound
                        ? candidate.offer().priceFen() >= bound
                        : candidate.offer().priceFen() <= bound)
                .toList();
        return filtered.isEmpty() ? candidates : filtered;
    }

    /**
     * 按类别策略排序后截断，控制搜索空间。
     *
     * <p>CPU/GPU 走「性能 + 价格」双端取样，内存与主板按平台分组保留配额，
     * 其余类别仍按画像排序取前 {@link #COMPONENT_CANDIDATE_LIMIT} 条。</p>
     */
    private List<Candidate> sortedTruncated(
            HardwareCategory category,
            List<Candidate> candidates,
            WorkloadProfile profile,
            boolean keepPriceTiers) {

        Comparator<Candidate> order = candidateOrder(category, profile);
        return switch (category) {
            case CPU, GPU -> performancePool(candidates, order, keepPriceTiers);
            case MEMORY -> cheapestPerGroup(
                    candidates, order, MEMORY_TYPE_CANDIDATE_LIMIT, BuildSolver::memoryTypeKey);
            case MOTHERBOARD -> cheapestPerGroup(
                    candidates, order, MOTHERBOARD_PLATFORM_CANDIDATE_LIMIT,
                    BuildSolver::platformKey);
            default -> topCandidates(candidates, order, COMPONENT_CANDIDATE_LIMIT);
        };
    }

    /**
     * CPU/GPU 候选池：性能前 8 + 最低价 4；预算场景再按价格分桶补足中端候选。
     *
     * <p>分桶只补充尚未入选的候选，按硬件 ID 去重，且每桶总数不超过
     * {@link #PRICE_BUCKET_CANDIDATE_QUOTA}，避免候选池无限制膨胀。</p>
     */
    private List<Candidate> performancePool(
            List<Candidate> candidates,
            Comparator<Candidate> order,
            boolean keepPriceTiers) {

        List<Candidate> sorted = new ArrayList<>(candidates);
        sorted.sort(order);
        if (!keepPriceTiers) {
            return topCandidates(sorted, order, PERFORMANCE_CANDIDATE_LIMIT);
        }
        int cheapQuota = Math.min(BUDGET_PRICE_TIER_QUOTA, PERFORMANCE_CANDIDATE_LIMIT / 2);
        int performanceQuota = PERFORMANCE_CANDIDATE_LIMIT - cheapQuota;
        Set<String> selectedIds = new HashSet<>();
        List<Candidate> selected = new ArrayList<>();
        for (Candidate candidate : sorted) {
            if (selected.size() >= performanceQuota) {
                break;
            }
            selected.add(candidate);
            selectedIds.add(candidate.hardware().hardwareId());
        }
        List<Candidate> byPrice = new ArrayList<>(sorted);
        byPrice.sort(priceFirstOrder());
        for (Candidate candidate : byPrice) {
            if (selected.size() >= PERFORMANCE_CANDIDATE_LIMIT) {
                break;
            }
            if (selectedIds.add(candidate.hardware().hardwareId())) {
                selected.add(candidate);
            }
        }
        fillPriceBucketQuota(sorted, selectedIds, selected);
        return List.copyOf(selected);
    }

    /**
     * 按价格分桶补足候选：每桶按画像顺序保留前 {@link #PRICE_BUCKET_CANDIDATE_QUOTA} 个。
     *
     * <p>已入选的候选也占用桶配额，保证补足后每桶总量固定，不放大搜索空间。</p>
     */
    private void fillPriceBucketQuota(
            List<Candidate> sortedByProfile,
            Set<String> selectedIds,
            List<Candidate> selected) {

        int[] bucketCounts = new int[PRICE_BUCKET_UPPER_BOUNDS_FEN.length + 1];
        for (Candidate candidate : selected) {
            bucketCounts[bucketIndexOf(candidate.offer().priceFen())]++;
        }
        for (Candidate candidate : sortedByProfile) {
            String hardwareId = candidate.hardware().hardwareId();
            if (selectedIds.contains(hardwareId)) {
                continue;
            }
            int bucket = bucketIndexOf(candidate.offer().priceFen());
            if (bucketCounts[bucket] >= PRICE_BUCKET_CANDIDATE_QUOTA) {
                continue;
            }
            bucketCounts[bucket]++;
            selectedIds.add(hardwareId);
            selected.add(candidate);
        }
    }

    private static int bucketIndexOf(long priceFen) {
        for (int index = 0; index < PRICE_BUCKET_UPPER_BOUNDS_FEN.length; index++) {
            if (priceFen < PRICE_BUCKET_UPPER_BOUNDS_FEN[index]) {
                return index;
            }
        }
        return PRICE_BUCKET_UPPER_BOUNDS_FEN.length;
    }

    /**
     * 按分组键保留每组前 N 个候选；排序与分组均显式声明，保证确定性。
     *
     * <p>分组而不是全库取前 N，是为了让每个平台/内存类型都保留可负担的候选；
     * 否则低价平台会占满配额，其他平台在兼容性校验阶段整池失配。</p>
     */
    private List<Candidate> cheapestPerGroup(
            List<Candidate> candidates,
            Comparator<Candidate> order,
            int limitPerGroup,
            Function<Candidate, String> groupKeyOf) {

        List<Candidate> sorted = new ArrayList<>(candidates);
        sorted.sort(order);
        Map<String, Integer> counts = new HashMap<>();
        List<Candidate> selected = new ArrayList<>();
        for (Candidate candidate : sorted) {
            String groupKey = groupKeyOf.apply(candidate);
            int count = counts.getOrDefault(groupKey, 0);
            if (count >= limitPerGroup) {
                continue;
            }
            counts.put(groupKey, count + 1);
            selected.add(candidate);
        }
        return List.copyOf(selected);
    }

    private List<Candidate> topCandidates(
            List<Candidate> candidates, Comparator<Candidate> order, int limit) {

        List<Candidate> sorted = new ArrayList<>(candidates);
        sorted.sort(order);
        return List.copyOf(sorted.subList(0, Math.min(limit, sorted.size())));
    }

    private static String memoryTypeKey(Candidate candidate) {
        return groupKeyOf(candidate.hardware().specifications().memoryType());
    }

    private static String platformKey(Candidate candidate) {
        return groupKeyOf(candidate.hardware().specifications().socket())
                + '|' + groupKeyOf(candidate.hardware().specifications().memoryType());
    }

    private static String groupKeyOf(String value) {
        return isBlank(value) ? UNKNOWN_GROUP_KEY : normalizeKey(value);
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

    /**
     * 按硬件聚合最低有效报价。
     *
     * <p>「指定组合生成方案」必须与求解使用同一取价口径，因此公开该方法而不是复制一份。</p>
     *
     * @param offers         全部报价
     * @param pricingDate    询价日期，用于判断有效期
     * @param requireVerified 是否只接受人工核验报价
     * @return 按硬件标识索引的最低有效报价
     */
    public Map<String, Offer> cheapestUsableOffers(
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

    /**
     * 由已选组合组装方案草稿。
     *
     * <p>求解命中与「按指定组合生成方案」共用这一份实现：报价、总价与评分只在这里计算，
     * 避免出现第二套价格口径。</p>
     *
     * @param requirements     需求，决定评分与逐件理由的文案口径
     * @param selection        已选八类硬件，必须完整
     * @param offersByHardware 按硬件标识索引的最低有效报价
     * @param benchmarkIndex   按硬件标识索引的跑分
     * @param catalogVersion   目录版本
     * @param offerDataStatus  报价数据状态
     * @return 方案草稿
     * @throws NullPointerException 任一类别缺少报价时
     */
    public BuildDraft toDraft(
            BuildRequirements requirements,
            HardwareSelection selection,
            Map<String, Offer> offersByHardware,
            Map<String, Benchmark> benchmarkIndex,
            String catalogVersion,
            String offerDataStatus) {

        Map<HardwareCategory, Offer> offers = new LinkedHashMap<>();
        Map<HardwareCategory, Benchmark> benchmarks = new LinkedHashMap<>();
        long totalPrice = 0L;
        for (HardwareCategory category : HardwareCategory.REQUIRED_CATEGORIES) {
            Hardware hardware = selection.get(category);
            Offer offer = Objects.requireNonNull(offersByHardware.get(hardware.hardwareId()),
                    () -> "缺少报价: " + hardware.hardwareId());
            totalPrice += offer.priceFen();
            offers.put(category, offer);
            Benchmark benchmark = benchmarkIndex.get(hardware.hardwareId());
            if (benchmark != null) {
                benchmarks.put(category, benchmark);
            }
        }
        CompatibilityReport report = compatibilityValidator.validate(selection);
        return new BuildDraft(
                requirements,
                selection,
                offers,
                benchmarks,
                totalPrice,
                report,
                BuildScoring.totalScore(requirements, selection.asMap(), benchmarkIndex),
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
