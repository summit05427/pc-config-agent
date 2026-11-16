package com.example.agent.pcbuild.application;

import com.example.agent.pcbuild.application.port.BenchmarkRepository;
import com.example.agent.pcbuild.application.port.OfferRepository;
import com.example.agent.pcbuild.domain.Benchmark;
import com.example.agent.pcbuild.domain.BuildDraft;
import com.example.agent.pcbuild.domain.BuildRequirements;
import com.example.agent.pcbuild.domain.BuildResult;
import com.example.agent.pcbuild.domain.CompatibilityCheck;
import com.example.agent.pcbuild.domain.CompatibilityReport;
import com.example.agent.pcbuild.domain.CompatibilityStatus;
import com.example.agent.pcbuild.domain.Hardware;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.HardwareSelection;
import com.example.agent.pcbuild.domain.Offer;
import com.example.agent.pcbuild.domain.PcBuildErrorCode;
import com.example.agent.pcbuild.domain.SolveOutcome;
import com.example.agent.pcbuild.web.dto.BuildResultResponse;
import com.example.agent.shared.error.BusinessException;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 配置求解、指定组合生成与校验的应用服务。
 *
 * <p>求解与指定组合成功时在同一事务内写入快照；失败不写库。校验接口不落库，也不要求用户令牌。</p>
 */
@Service
@RequiredArgsConstructor
public class BuildSolveService {

    /**
     * 指定组合不携带需求，统一按默认场景与无预算生成：评分与逐件理由沿用默认口径。
     */
    private static final BuildRequirements COMPOSE_REQUIREMENTS =
            new BuildRequirements(null, BuildRequirements.DEFAULT_SCENARIO, null, null, false);

    private final BuildSolver solver;

    private final CompatibilityValidator compatibilityValidator;

    private final HardwareCatalogService hardwareCatalogService;

    private final BenchmarkRepository benchmarkRepository;

    private final OfferRepository offerRepository;

    private final BuildSnapshotService buildSnapshotService;

    /**
     * 求解并持久化快照。
     *
     * @param userId       所属用户
     * @param requirements 需求
     * @return 成功方案或结构化失败
     */
    @Transactional
    public SolveExecutionResult solve(UUID userId, BuildRequirements requirements) {
        SolveOutcome outcome = solver.solve(
                requirements,
                hardwareCatalogService.listSolverEligible(),
                offerRepository.findAll(),
                benchmarkRepository.findAll(),
                hardwareCatalogService.catalogVersion(),
                offerRepository.dataStatus(),
                LocalDate.now());
        if (!outcome.isSolved()) {
            return SolveExecutionResult.failed(outcome.failure());
        }
        BuildResult result = BuildResult.fromDraft(
                userId, UUID.randomUUID(), outcome.build(), Instant.now());
        buildSnapshotService.save(result);
        return SolveExecutionResult.solved(result);
    }

    /**
     * 按指定八类硬件生成方案并持久化快照。
     *
     * <p>价格与总价只来自 {@link OfferRepository} 的最低有效报价，不接受调用方传入价格；
     * 任一选中硬件没有可用报价时返回结构化失败，不用 0 或历史价补齐。
     * 兼容性存在硬冲突时同样返回结构化失败，快照只保存可用方案。</p>
     *
     * @param userId       所属用户
     * @param hardwareIds  八类硬件标识
     * @param budgetMaxFen 预算上限，单位分；{@code null} 表示不限制
     * @return 已落库方案
     * @throws BusinessException 缺类别或类别不符 400 {@code 40303}；无可用报价 409 {@code 40307}；
     *                           存在硬冲突 422 {@code 40308}；超出预算 422 {@code 40309}
     */
    @Transactional
    public BuildResult composeAndSnapshot(
            UUID userId, Map<HardwareCategory, String> hardwareIds, Long budgetMaxFen) {
        HardwareSelection selection = HardwareSelection.from(resolveSelection(hardwareIds));
        Map<String, Offer> offersByHardware = solver.cheapestUsableOffers(
                offerRepository.findAll(), LocalDate.now(), false);
        requireOffers(selection, offersByHardware);
        BuildDraft draft = solver.toDraft(
                COMPOSE_REQUIREMENTS,
                selection,
                offersByHardware,
                benchmarkIndex(),
                hardwareCatalogService.catalogVersion(),
                offerRepository.dataStatus());
        requireCompatible(draft.compatibilityReport());
        requireWithinBudget(draft.totalPriceFen(), budgetMaxFen);
        BuildResult result = BuildResult.fromDraft(userId, UUID.randomUUID(), draft, Instant.now());
        buildSnapshotService.save(result);
        return result;
    }

    /**
     * 校验一套指定配置。
     *
     * @param hardwareIds 八类硬件的标识
     * @return 兼容性报告
     * @throws BusinessException 类别缺失、硬件不存在或类别不符
     */
    public CompatibilityReport validate(Map<HardwareCategory, String> hardwareIds) {
        return compatibilityValidator.validate(HardwareSelection.from(resolveSelection(hardwareIds)));
    }

    /**
     * 部分校验：只校验调用方已选组件之间的兼容性。
     *
     * <p>规则实现与 {@link #validate(Map)} 是同一套（{@link CompatibilityValidator#validatePartial}），
     * 区别仅在于依赖类别未选全的规则不执行；已执行规则遇到字段缺失仍返回 {@code UNKNOWN}。
     * 不落库，也不要求用户令牌。</p>
     *
     * @param hardwareIds 任意子集的类别到硬件标识映射
     * @return 部分兼容性报告
     * @throws BusinessException 组件为空、类别不符 400 {@code 40303}；硬件不存在 404 {@code 40301}
     */
    public CompatibilityReport validatePartial(Map<HardwareCategory, String> hardwareIds) {
        return compatibilityValidator.validatePartial(
                HardwareSelection.from(resolvePartialSelection(hardwareIds)));
    }

    /**
     * 解析部分组合的硬件标识并校验类别归属。
     *
     * <p>与 {@link #resolveSelection(Map)} 的差异只有「允许缺类别」：缺类别表示调用方本次
     * 不关心该组件，而不是配置不完整。</p>
     *
     * @param hardwareIds 部分类别到硬件标识的映射
     * @return 已解析的硬件，按类别索引
     * @throws BusinessException 没有任何组件 400 {@code 40303}；类别不符 400 {@code 40303}；
     *                           硬件不存在 404 {@code 40301}
     */
    private Map<HardwareCategory, Hardware> resolvePartialSelection(
            Map<HardwareCategory, String> hardwareIds) {

        Map<HardwareCategory, Hardware> resolved = new EnumMap<>(HardwareCategory.class);
        for (HardwareCategory category : HardwareCategory.REQUIRED_CATEGORIES) {
            String hardwareId = hardwareIds.get(category);
            if (hardwareId == null || hardwareId.isBlank()) {
                continue;
            }
            Hardware hardware = hardwareCatalogService.require(hardwareId);
            if (hardware.category() != category) {
                throw new BusinessException(PcBuildErrorCode.BUILD_INCOMPLETE,
                        "硬件 " + hardwareId + " 属于 " + hardware.category().name()
                                + "，但被放在 " + category.name());
            }
            resolved.put(category, hardware);
        }
        if (resolved.isEmpty()) {
            throw new BusinessException(PcBuildErrorCode.BUILD_INCOMPLETE, "至少需要一个硬件组件");
        }
        return resolved;
    }

    /**
     * 解析八类硬件标识并校验类别归属；解析逻辑由校验与指定组合生成共用。
     *
     * @param hardwareIds 八类硬件标识
     * @return 按类别索引的硬件
     * @throws BusinessException 类别缺失或类别不符 400 {@code 40303}；硬件不存在 404 {@code 40301}
     */
    private Map<HardwareCategory, Hardware> resolveSelection(Map<HardwareCategory, String> hardwareIds) {
        Map<HardwareCategory, Hardware> resolved = new EnumMap<>(HardwareCategory.class);
        for (HardwareCategory category : HardwareCategory.REQUIRED_CATEGORIES) {
            String hardwareId = hardwareIds.get(category);
            if (hardwareId == null || hardwareId.isBlank()) {
                throw new BusinessException(PcBuildErrorCode.BUILD_INCOMPLETE,
                        "缺少类别: " + category.name());
            }
            Hardware hardware = hardwareCatalogService.require(hardwareId);
            if (hardware.category() != category) {
                throw new BusinessException(PcBuildErrorCode.BUILD_INCOMPLETE,
                        "硬件 " + hardwareId + " 属于 " + hardware.category().name()
                                + "，但被放在 " + category.name());
            }
            resolved.put(category, hardware);
        }
        return resolved;
    }

    private void requireOffers(HardwareSelection selection, Map<String, Offer> offersByHardware) {
        List<String> missing = new ArrayList<>();
        for (HardwareCategory category : HardwareCategory.REQUIRED_CATEGORIES) {
            String hardwareId = selection.get(category).hardwareId();
            if (offersByHardware.get(hardwareId) == null) {
                missing.add(category.name() + "(" + hardwareId + ")");
            }
        }
        if (!missing.isEmpty()) {
            throw new BusinessException(PcBuildErrorCode.BUILD_OFFER_UNAVAILABLE,
                    "以下硬件没有可用报价: " + String.join("、", missing));
        }
    }

    private void requireCompatible(CompatibilityReport report) {
        if (!report.hasFailure()) {
            return;
        }
        String failedRules = report.checks().stream()
                .filter(check -> check.status() == CompatibilityStatus.FAIL)
                .map(CompatibilityCheck::ruleId)
                .collect(Collectors.joining("、"));
        throw new BusinessException(PcBuildErrorCode.BUILD_INCOMPATIBLE,
                "所选硬件存在兼容性冲突: " + failedRules);
    }

    private void requireWithinBudget(long totalPriceFen, Long budgetMaxFen) {
        if (budgetMaxFen == null || totalPriceFen <= budgetMaxFen) {
            return;
        }
        throw new BusinessException(PcBuildErrorCode.BUDGET_EXCEEDED,
                "所选配置总价 " + totalPriceFen + " 分超过预算上限 " + budgetMaxFen + " 分");
    }

    private Map<String, Benchmark> benchmarkIndex() {
        Map<String, Benchmark> index = new HashMap<>();
        for (Benchmark benchmark : benchmarkRepository.findAll()) {
            index.put(benchmark.hardwareId(), benchmark);
        }
        return index;
    }

    /**
     * 读取当前用户的方案快照。
     *
     * @param userId  用户公开 ID
     * @param buildId 快照标识
     * @return 响应
     */
    public BuildResultResponse requireBuild(UUID userId, UUID buildId) {
        return buildSnapshotService.requireOwned(userId, buildId);
    }
}
