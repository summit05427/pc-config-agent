package com.example.agent.pcbuild.application;

import com.example.agent.pcbuild.application.port.BenchmarkRepository;
import com.example.agent.pcbuild.application.port.OfferRepository;
import com.example.agent.pcbuild.domain.BuildRequirements;
import com.example.agent.pcbuild.domain.BuildResult;
import com.example.agent.pcbuild.domain.CompatibilityReport;
import com.example.agent.pcbuild.domain.Hardware;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.HardwareSelection;
import com.example.agent.pcbuild.domain.PcBuildErrorCode;
import com.example.agent.pcbuild.domain.SolveOutcome;
import com.example.agent.pcbuild.web.dto.BuildResultResponse;
import com.example.agent.shared.error.BusinessException;
import java.time.Instant;
import java.time.LocalDate;
import java.util.EnumMap;
import java.util.Map;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 配置求解与校验的应用服务。
 *
 * <p>求解成功时在同一事务内写入快照；求解失败不写库。校验接口不落库，也不要求用户令牌。</p>
 */
@Service
@RequiredArgsConstructor
public class BuildSolveService {

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
     * 校验一套指定配置。
     *
     * @param hardwareIds 八类硬件的标识
     * @return 兼容性报告
     * @throws BusinessException 类别缺失、硬件不存在或类别不符
     */
    public CompatibilityReport validate(Map<HardwareCategory, String> hardwareIds) {
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
        return compatibilityValidator.validate(HardwareSelection.from(resolved));
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
