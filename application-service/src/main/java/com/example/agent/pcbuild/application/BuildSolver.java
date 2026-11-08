package com.example.agent.pcbuild.application;

import com.example.agent.pcbuild.domain.Benchmark;
import com.example.agent.pcbuild.domain.BuildDraft;
import com.example.agent.pcbuild.domain.BuildRequirements;
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
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
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

    /** 每 GB 内存的评分加成。 */
    private static final long MEMORY_BONUS_PER_GB = 500L;

    /** 每 GB 存储的评分加成。 */
    private static final long STORAGE_BONUS_PER_GB = 20L;

    private static final int MEMORY_BONUS_CAP_GB = 64;

    private static final int STORAGE_BONUS_CAP_GB = 2048;

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
            HardwareCategory.MEMORY, List.of(CompatibilityRule.MOTHERBOARD_MEMORY_TYPE),
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

        Map<HardwareCategory, List<Candidate>> pools = new LinkedHashMap<>();
        Map<String, Integer> candidateCounts = new LinkedHashMap<>();
        List<String> missingCategories = new ArrayList<>();
        for (HardwareCategory category : HardwareCategory.REQUIRED_CATEGORIES) {
            List<Candidate> pool = buildPool(category, catalog, cheapestOffers, benchmarkIndex, requirements);
            pools.put(category, pool);
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
            SearchContext probe = new SearchContext(requirements, pools, benchmarkIndex);
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

    private List<Candidate> buildPool(
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
            candidates.add(new Candidate(hardware, offer, benchmark, performanceScore));
        }
        candidates.sort(candidateOrder(category));
        int limit = category == HardwareCategory.CPU || category == HardwareCategory.GPU
                ? PERFORMANCE_CANDIDATE_LIMIT
                : COMPONENT_CANDIDATE_LIMIT;
        return List.copyOf(candidates.subList(0, Math.min(limit, candidates.size())));
    }

    private Comparator<Candidate> candidateOrder(HardwareCategory category) {
        if (category == HardwareCategory.CPU || category == HardwareCategory.GPU) {
            return Comparator.comparingLong(Candidate::performanceScore).reversed()
                    .thenComparingLong(candidate -> candidate.offer().priceFen())
                    .thenComparing(candidate -> candidate.hardware().hardwareId());
        }
        return Comparator.comparingLong((Candidate candidate) -> candidate.offer().priceFen())
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
        BuildRequirements requirements = context.requirements;
        long cpuScore = benchmarkScore(context, selection.cpu());
        long gpuScore = benchmarkScore(context, selection.gpu());
        long weighted = (cpuScore * requirements.scenario().cpuWeight()
                + gpuScore * requirements.scenario().gpuWeight()) / 100L;
        long memoryCapacity = Math.min(capacityGb(selection.memory()), MEMORY_BONUS_CAP_GB);
        long storageCapacity = Math.min(capacityGb(selection.storage()), STORAGE_BONUS_CAP_GB);
        return weighted
                + memoryCapacity * MEMORY_BONUS_PER_GB
                + storageCapacity * STORAGE_BONUS_PER_GB;
    }

    private long benchmarkScore(SearchContext context, Hardware hardware) {
        if (hardware == null) {
            return 0L;
        }
        Benchmark benchmark = context.benchmarkIndex.get(hardware.hardwareId());
        return benchmark == null ? 0L : Math.max(0L, benchmark.scoreAsLong());
    }

    private long capacityGb(Hardware hardware) {
        if (hardware == null || hardware.specifications().capacityGb() == null) {
            return 0L;
        }
        return Math.max(0, hardware.specifications().capacityGb());
    }

    private boolean isBetter(SearchContext context, long score, long price, String ids) {
        if (context.bestSelection == null) {
            return true;
        }
        if (context.requirements.hasBudget()) {
            if (score != context.bestScore) {
                return score > context.bestScore;
            }
        } else {
            long value = valueOf(score, price);
            long bestValue = valueOf(context.bestScore, context.bestPrice);
            if (value != bestValue) {
                return value > bestValue;
            }
            if (score != context.bestScore) {
                return score > context.bestScore;
            }
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
            long performanceScore) {
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
