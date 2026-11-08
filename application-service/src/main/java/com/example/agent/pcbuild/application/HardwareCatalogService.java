package com.example.agent.pcbuild.application;

import com.example.agent.pcbuild.application.port.HardwareCatalogRepository;
import com.example.agent.pcbuild.domain.Hardware;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.PcBuildErrorCode;
import com.example.agent.shared.error.BusinessException;
import java.util.Comparator;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

/**
 * 硬件目录查询服务。
 *
 * <p>排序键固定为「类别枚举顺序 → hardware_id」，同一份 fixture 每次返回相同顺序，
 * 供 Agent 稳定展示与求解器复现。</p>
 */
@Service
@RequiredArgsConstructor
public class HardwareCatalogService {

    private static final Comparator<Hardware> STABLE_ORDER = Comparator
            .comparingInt((Hardware hardware) -> hardware.category().ordinal())
            .thenComparing(Hardware::hardwareId);

    private final HardwareCatalogRepository repository;

    /**
     * 查询候选硬件。
     *
     * @param category 类别过滤，可为 {@code null}
     * @return 按稳定顺序排列的硬件列表
     */
    public List<Hardware> listCandidates(HardwareCategory category) {
        return repository.findAll().stream()
                .filter(hardware -> category == null || hardware.category() == category)
                .sorted(STABLE_ORDER)
                .toList();
    }

    /**
     * @return 仅包含可参与求解的硬件
     */
    public List<Hardware> listSolverEligible() {
        return repository.findAll().stream()
                .filter(Hardware::isSolverEligible)
                .sorted(STABLE_ORDER)
                .toList();
    }

    /**
     * @param hardwareId 硬件标识
     * @return 硬件详情
     * @throws BusinessException 不存在时 404 {@code 40301}
     */
    public Hardware require(String hardwareId) {
        return repository.findById(hardwareId)
                .orElseThrow(() -> new BusinessException(PcBuildErrorCode.HARDWARE_NOT_FOUND));
    }

    /**
     * @return 目录版本
     */
    public String catalogVersion() {
        return repository.catalogVersion();
    }
}
